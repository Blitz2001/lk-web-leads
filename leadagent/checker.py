"""Website audit: fetch the homepage once and turn what we see into plain-language findings.

Every finding has:
  code      machine id
  points    how much it adds to the opportunity score
  pitch     a sentence you could say to the owner (no jargon)
  offer     which of your services it supports: website | wordpress | custom | chatbot
"""
from __future__ import annotations

import datetime as dt
import re
import time
from dataclasses import asdict, dataclass, field

import requests
from bs4 import BeautifulSoup

from .util import domain_of

UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36 LeadAgentAudit/1.0"
)

SOCIAL_ONLY = {
    "facebook.com", "m.facebook.com", "fb.com", "fb.me", "instagram.com", "linktr.ee",
    "wa.me", "api.whatsapp.com", "tiktok.com", "youtube.com", "twitter.com", "x.com",
}
LISTING_ONLY = {
    "booking.com", "tripadvisor.com", "airbnb.com", "agoda.com", "expedia.com",
    "hotels.com", "ikman.lk", "lankabusinessdirectory.com", "yellowpages.lk",
}
# Free subdomains that look unprofessional. business.site = Google Business
# Profile websites, which Google shut down in 2024: those links are dead.
FREE_HOSTS = (
    ".business.site", ".wixsite.com", ".blogspot.com", ".weebly.com", ".wordpress.com",
    ".godaddysites.com", ".webnode.com", ".site123.me", ".jimdosite.com", ".mystrikingly.com",
    ".carrd.co", ".000webhostapp.com", ".github.io", ".netlify.app", ".vercel.app",
)
PARKED_PATTERNS = [
    r"domain (name )?(is|may be) for sale", r"buy this domain", r"this domain has expired",
    r"domain (has )?expired", r"account (has been )?suspended", r"parked (free|domain)",
    r"sedoparking", r"hugedomains", r"dan\.com", r"default web site page",
    r"apache2? (ubuntu |debian )?default page", r"welcome to nginx", r"index of /",
    r"cpanel.{0,40}(default|coming soon)", r"web hosting.{0,30}account.{0,30}(inactive|suspended)",
]
CONSTRUCTION_PATTERNS = [r"under construction", r"coming soon", r"site is under maintenance", r"launching soon"]
CHAT_SIGNATURES = {
    "tawk.to": "Tawk.to", "embed.tawk.to": "Tawk.to", "tidio": "Tidio", "crisp.chat": "Crisp",
    "intercom": "Intercom", "zendesk": "Zendesk", "livechatinc": "LiveChat", "drift.com": "Drift",
    "hubspot": "HubSpot chat", "freshchat": "Freshchat", "chatbot.com": "ChatBot",
    "manychat": "ManyChat", "botpress": "Botpress", "voiceflow": "Voiceflow", "chatbase": "Chatbase",
    "elfsight.com/whatsapp": "WhatsApp widget", "getbutton.io": "WhatsApp button",
    "joinchat": "WhatsApp button", "wa.me/": "WhatsApp link", "api.whatsapp.com/send": "WhatsApp link",
    "fb-customerchat": "Messenger chat", "customerchat": "Messenger chat",
}
BOOKING_SIGNATURES = [
    "book now", "check availability", "reserve", "booking engine", "cloudbeds", "sirvoy",
    "beds24", "simplebooking", "little hotelier", "littlehotelier", "synxis", "ezee", "resrequest",
    "opentable", "calendly", "setmore", "fresha", "book an appointment", "make an appointment",
]


@dataclass
class Finding:
    code: str
    points: int
    pitch: str
    offer: str


@dataclass
class Audit:
    url: str | None
    final_url: str | None = None
    status: int | None = None
    reachable: bool = False
    https: bool = False
    load_seconds: float | None = None
    html_kb: int | None = None
    platform: str | None = None
    platform_version: str | None = None
    title: str | None = None
    copyright_year: int | None = None
    has_viewport: bool = False
    has_chat: str | None = None
    has_booking: bool = False
    has_contact_form: bool = False
    has_tel_link: bool = False
    emails_found: list[str] = field(default_factory=list)
    phones_found: list[str] = field(default_factory=list)
    facebook_found: str | None = None
    pagespeed_mobile: int | None = None
    findings: list[Finding] = field(default_factory=list)
    score: int = 0
    tier: str = "cold"
    error: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def add(self, code: str, points: int, pitch: str, offer: str) -> None:
        self.findings.append(Finding(code, points, pitch, offer))


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_EMAIL_JUNK = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js)$|sentry|wixpress|example\.(com|lk)|domain\.com|yourdomain|@2x", re.I)


def _collect_contacts(a: "Audit", html: str, soup: BeautifulSoup) -> None:
    """Pull emails, phone/WhatsApp numbers and a Facebook link out of a page."""
    from .util import normalize_lk_phone

    emails = set(a.emails_found)
    deobf = re.sub(r"\s*[\[\(\{]\s*at\s*[\]\)\}]\s*", "@", html, flags=re.I)
    deobf = re.sub(r"\s*[\[\(\{]\s*dot\s*[\]\)\}]\s*", ".", deobf, flags=re.I)
    for e in _EMAIL_RE.findall(deobf):
        if not _EMAIL_JUNK.search(e):
            emails.add(e.lower())
    a.emails_found = sorted(emails)[:3]

    phones = list(a.phones_found)
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        num = None
        if href.lower().startswith("tel:"):
            num = normalize_lk_phone(href[4:])
        elif "wa.me/" in href or "api.whatsapp.com/send" in href:
            m = re.search(r"(?:wa\.me/|phone=)\+?(\d{9,13})", href)
            num = normalize_lk_phone(m.group(1)) if m else None
        elif "facebook.com/" in href and not a.facebook_found and "sharer" not in href:
            a.facebook_found = href.split("?")[0]
        if num and num not in phones:
            phones.append(num)
    if not phones:  # plain-text numbers like 077 123 4567 or +94 11 234 5678
        text = soup.get_text(" ", strip=True)
        for m in re.findall(r"(?:\+94|0094|0)\s?\(?\d{2}\)?[\s-]?\d{3}[\s-]?\d{4}", text)[:5]:
            num = normalize_lk_phone(m)
            if num and num not in phones:
                phones.append(num)
    a.phones_found = phones[:3]


def _contact_link(soup: BeautifulSoup, base: str) -> str | None:
    from urllib.parse import urljoin, urlparse

    host = urlparse(base).hostname
    for tag in soup.find_all("a", href=True):
        label = (tag.get_text(" ", strip=True) + " " + tag["href"]).lower()
        if any(k in label for k in ("contact", "reach us", "get in touch", "location")):
            url = urljoin(base, tag["href"])
            if urlparse(url).hostname == host and url.split("#")[0] != base.split("#")[0]:
                return url
    return None


def _fetch(url: str, timeout: float) -> tuple[requests.Response | None, float, str | None]:
    t0 = time.monotonic()
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=timeout, allow_redirects=True)
        return r, time.monotonic() - t0, None
    except requests.exceptions.SSLError as e:
        return None, time.monotonic() - t0, f"ssl: {e.__class__.__name__}"
    except requests.exceptions.ConnectionError as e:
        msg = str(e)
        kind = "dns" if ("NameResolution" in msg or "Name or service not known" in msg or "getaddrinfo" in msg) else "connect"
        return None, time.monotonic() - t0, kind
    except requests.exceptions.Timeout:
        return None, time.monotonic() - t0, "timeout"
    except requests.RequestException as e:
        return None, time.monotonic() - t0, e.__class__.__name__


def detect_platform(html: str, soup: BeautifulSoup, headers: dict) -> tuple[str | None, str | None]:
    gen = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    gen_c = (gen.get("content") or "") if gen else ""
    m = re.search(r"WordPress\s*([\d.]+)?", gen_c, re.I)
    if m or "/wp-content/" in html or "/wp-includes/" in html:
        ver = m.group(1) if m and m.group(1) else None
        if not ver:
            vm = re.search(r"/wp-includes/[^\"']+\?ver=(\d+\.\d+(?:\.\d+)?)", html)
            ver = vm.group(1) if vm else None
        return "WordPress", ver
    checks = [
        ("Wix", ["static.wixstatic.com", "wix.com website builder", "_wixcssimports"]),
        ("Squarespace", ["squarespace.com", "static1.squarespace"]),
        ("Shopify", ["cdn.shopify.com"]),
        ("Weebly", ["weebly.com", "editmysite.com"]),
        ("Blogger", ["blogger.com", "blogspot.com"]),
        ("Joomla", ["/media/jui/", "joomla!"]),
        ("Drupal", ["drupal.settings", "/sites/default/files/"]),
        ("GoDaddy Builder", ["img1.wsimg.com", "godaddy website builder"]),
        ("Webflow", ["webflow.js", "data-wf-page"]),
        ("Next.js", ["/_next/static/"]),
        ("Framer", ["framerusercontent.com"]),
    ]
    low = html.lower()
    for name, sigs in checks:
        if any(s in low for s in sigs) or name.lower() in gen_c.lower():
            return name, None
    if gen_c:
        return gen_c.split()[0], None
    if "x-powered-by" in {k.lower() for k in headers}:
        return None, None
    return None, None


def _version_tuple(v: str | None) -> tuple[int, ...]:
    if not v:
        return ()
    try:
        return tuple(int(x) for x in v.split(".")[:3])
    except ValueError:
        return ()


def pagespeed_score(url: str) -> int | None:
    """Google PageSpeed Insights mobile performance score (0-100). Free; an optional
    PAGESPEED_API_KEY (free from Google Cloud) raises the rate limit."""
    import os

    params = {"url": url, "strategy": "mobile", "category": "performance"}
    if os.environ.get("PAGESPEED_API_KEY"):
        params["key"] = os.environ["PAGESPEED_API_KEY"]
    try:
        r = requests.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed", params=params, timeout=90)
        if r.status_code != 200:
            return None
        s = r.json()["lighthouseResult"]["categories"]["performance"]["score"]
        return round(s * 100) if s is not None else None
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None


def audit_site(url: str | None, category: str = "", timeout: float = 20, pagespeed: bool = False) -> Audit:
    a = Audit(url=url)
    year = dt.date.today().year

    # ---- no website at all
    if not url:
        a.add("no_website", 60, "you don't have a website yet, so people who search for you on Google only find a map pin or a listing", "website")
        return _finish(a, category)

    dom = domain_of(url)
    if dom in SOCIAL_ONLY or any(dom.endswith("." + s) for s in SOCIAL_ONLY):
        a.add("social_only", 50, "your 'website' link goes to a social media page, which customers can't easily book or enquire through and which you don't fully control", "website")
        return _finish(a, category)
    if dom in LISTING_ONLY or any(dom.endswith("." + s) for s in LISTING_ONLY):
        a.add("listing_only", 45, "your website link points to a booking/listing site, so every enquiry goes through a platform that takes commission", "website")
        return _finish(a, category)
    if dom.endswith(".business.site"):
        a.add("dead_google_site", 55, "your Google listing still links to a business.site page, which Google shut down in 2024, so that link is now dead", "website")
        return _finish(a, category)

    # ---- fetch (prefer https)
    https_url = re.sub(r"^http://", "https://", url, flags=re.I)
    r, secs, err = _fetch(https_url, timeout)
    ssl_broken = bool(err and err.startswith("ssl"))
    if r is None:
        r2, secs2, err2 = _fetch(re.sub(r"^https://", "http://", url, flags=re.I), timeout)
        if r2 is not None:
            r, secs, err = r2, secs2, None
        else:
            err = err2 or err
    a.load_seconds = round(secs, 2)

    if r is None:
        a.error = err
        if err == "dns":
            a.add("domain_dead", 55, f"{dom} doesn't load at all (the domain doesn't resolve), so anyone clicking it from Google or your listing hits an error", "website")
        elif err == "timeout":
            a.add("timeout", 45, f"{dom} took more than {int(timeout)} seconds and never loaded when I tried it", "website")
        else:
            a.add("unreachable", 50, f"{dom} doesn't load. The browser shows a connection error", "website")
        return _finish(a, category)

    a.status = r.status_code
    a.final_url = r.url
    a.https = r.url.lower().startswith("https://")
    a.reachable = r.status_code < 400
    html = r.text or ""
    a.html_kb = len(r.content) // 1024
    low = html.lower()

    if r.status_code >= 400:
        a.add("http_error", 50, f"{dom} returns an error page (HTTP {r.status_code}) instead of your site", "website")
        return _finish(a, category)

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).lower()

    if any(re.search(p, low) for p in PARKED_PATTERNS) and len(text) < 3000:
        a.add("parked", 55, f"{dom} shows a parked/expired or default hosting page instead of your business", "website")
        return _finish(a, category)
    if any(re.search(p, text) for p in CONSTRUCTION_PATTERNS) and len(text) < 1500:
        a.add("under_construction", 45, f"{dom} still shows an 'under construction / coming soon' page", "website")

    if len(text) < 200 and not soup.find("script", src=True) and not a.findings:
        a.add("near_empty", 25, "the homepage has almost no content: no services, prices or reasons to choose you", "website")

    # ---- facts
    a.title = (soup.title.string or "").strip()[:120] if soup.title and soup.title.string else None
    a.platform, a.platform_version = detect_platform(html, soup, dict(r.headers))
    a.has_viewport = bool(soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}))
    years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", html, re.I)]
    years = [y for y in years if 1995 <= y <= year]
    a.copyright_year = max(years) if years else None
    for sig, name in CHAT_SIGNATURES.items():
        if sig in low:
            a.has_chat = name
            break
    a.has_booking = any(s in low for s in BOOKING_SIGNATURES)
    a.has_contact_form = bool(soup.find("form")) and any(
        k in low for k in ("contact", "enquir", "inquir", "message", "wpcf7", "wpforms", "gform")
    )
    a.has_tel_link = 'href="tel:' in low or "href='tel:" in low
    _collect_contacts(a, html, soup)
    # Contact details often live on /contact: fetch it once if the homepage had none.
    if not a.emails_found or not a.phones_found:
        link = _contact_link(soup, r.url)
        if link:
            cr, _, _ = _fetch(link, min(timeout, 10))
            if cr is not None and cr.status_code < 400 and "html" in cr.headers.get("Content-Type", "html"):
                ch = cr.text or ""
                _collect_contacts(a, ch, BeautifulSoup(ch, "html.parser"))
                if not a.has_contact_form and BeautifulSoup(ch, "html.parser").find("form"):
                    a.has_contact_form = True

    # ---- findings (pitch-ready language)
    if ssl_broken or not a.https:
        a.add("no_https", 15, "the site isn't secure (no valid HTTPS), so Chrome shows 'Not secure' next to your name, which puts customers off", "website")
    if not a.has_viewport:
        a.add("not_mobile", 20, "the site isn't mobile-friendly: on a phone the text is tiny and you have to pinch-zoom, and most of your visitors are on phones", "website")
    if pagespeed:
        a.pagespeed_mobile = pagespeed_score(a.final_url or url)
        if a.pagespeed_mobile is not None and a.pagespeed_mobile < 50:
            a.add("low_pagespeed", 15, f"Google's own PageSpeed test scores the site {a.pagespeed_mobile}/100 on mobile, which hurts your Google ranking", "custom")
    if a.load_seconds and a.load_seconds > 4:
        a.add("slow", 10, f"the homepage took about {a.load_seconds:.0f} seconds to load on my test; people usually leave after 3", "custom")
    if a.html_kb and a.html_kb > 1500:
        a.add("heavy", 5, "the page is very heavy, which makes it slow on mobile data", "custom")
    if a.copyright_year and a.copyright_year <= year - 3:
        a.add("stale", 10, f"the footer still says © {a.copyright_year}, which makes the site look abandoned", "website")
    host = domain_of(a.final_url)
    if host.endswith(FREE_HOSTS):
        a.add("free_subdomain", 15, f"the site lives on a free address ({host}) instead of your own domain, which looks less trustworthy", "website")
    if a.platform == "WordPress" and _version_tuple(a.platform_version) and _version_tuple(a.platform_version) < (6, 0):
        a.add("old_wordpress", 15, f"it runs an outdated WordPress version ({a.platform_version}), which is a real security risk (old WordPress sites get hacked often)", "wordpress")
    if a.platform in ("Wix", "Weebly", "GoDaddy Builder", "Blogger", "Joomla"):
        a.add("weak_builder", 5, f"it's built on {a.platform}, which limits speed, SEO and what you can add later", "custom")
    jq = re.search(r"jquery[.-]?(1\.\d+(?:\.\d+)?)", low)
    if jq and _version_tuple(jq.group(1)) < (1, 12):
        a.add("old_code", 5, "it uses very old code libraries, a sign it hasn't been maintained", "custom")
    if "<frameset" in low or ".swf" in low or "<marquee" in low:
        a.add("ancient", 15, "it uses very old web technology (frames/Flash/marquee) that modern phones don't display properly", "custom")
    if not soup.find("meta", attrs={"name": re.compile("^description$", re.I)}) or not a.title:
        a.add("no_seo_basics", 5, "the page is missing basic Google info (title/description), so it shows up poorly in search results", "website")
    if not a.has_contact_form and not a.has_tel_link and not a.has_chat:
        a.add("no_cta", 10, "there's no quick way to contact you from the page: no tap-to-call, WhatsApp or enquiry form", "chatbot")
    if not a.has_chat:
        a.add("no_chat", 10, "there's no chat or WhatsApp button, so visitors with a quick question (prices, availability, opening hours) just leave", "chatbot")
    if category in ("hotels", "restaurants", "clinics", "salons", "tours", "gyms") and not a.has_booking:
        a.add("no_booking", 10, "there's no way to book or check availability directly on the site", "chatbot")

    return _finish(a, category)


def _finish(a: Audit, category: str) -> Audit:
    a.score = min(100, sum(f.points for f in a.findings))
    a.tier = "hot" if a.score >= 50 else "warm" if a.score >= 25 else "cold"
    return a

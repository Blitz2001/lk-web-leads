"""Decide what to offer and draft the message. You review and send it yourself.

Two modes:
  * templates (default, free, offline)
  * --ai: Claude rewrites the draft from the same facts (needs `pip install anthropic`
    and ANTHROPIC_API_KEY). It can also write in Sinhala or Tamil.
"""
from __future__ import annotations

import json
import os
import re

from .util import is_mobile

CATEGORY_INFO = {
    "hotels": ("hotels and guest houses", "your rooms, rates, photos and a direct-booking button", "direct booking requests"),
    "restaurants": ("restaurants and cafes", "your menu, photos, opening hours and table reservations", "reservations and orders"),
    "clinics": ("clinics and medical practices", "your doctors, services, channelling times and appointment requests", "appointment requests"),
    "salons": ("salons and spas", "your services, price list, gallery and online appointments", "appointments"),
    "tours": ("tour operators", "your tour packages, itineraries, reviews and enquiry forms", "tour enquiries"),
    "gyms": ("gyms and fitness centres", "your memberships, class timetable and trainers", "membership sign-ups"),
    "education": ("institutes and tuition classes", "your courses, timetables, results and online registration", "student registrations"),
    "retail": ("shops", "your products, prices, location and WhatsApp ordering", "orders and enquiries"),
    "auto": ("vehicle sales and service businesses", "your vehicles/services, prices and service bookings", "service bookings and enquiries"),
    "realestate": ("real estate and construction companies", "your projects, listings and enquiry forms", "property enquiries"),
    "professional": ("professional firms", "your services, team and consultation requests", "consultation requests"),
}
DEFAULT_INFO = ("local businesses", "your services, photos, location and contact options", "enquiries")

URGENT = {"domain_dead", "unreachable", "timeout", "http_error", "parked", "dead_google_site"}
NO_SITE = {"no_website", "social_only", "listing_only"}


def choose_offer(lead: dict, audit: dict, profile: dict) -> dict:
    codes = {f["code"] for f in audit["findings"]}
    site_points = sum(f["points"] for f in audit["findings"] if f["offer"] in ("website", "wordpress", "custom"))
    custom_first = set(profile.get("custom_first_categories", ["hotels", "tours", "realestate"]))

    if codes & (NO_SITE | URGENT) or "under_construction" in codes:
        kind = "new_site" if codes & NO_SITE else "rebuild"
        build = "custom" if lead.get("category") in custom_first else "wordpress"
    elif site_points >= 25:
        kind = "redesign"
        if audit.get("platform") == "WordPress":
            build = "wordpress"
        elif codes & {"slow", "weak_builder", "ancient", "old_code", "heavy"}:
            build = "custom"
        else:
            build = "custom" if lead.get("category") in custom_first else "wordpress"
    else:
        kind, build = None, None

    wants_chat = bool(codes & {"no_chat", "no_booking", "no_cta"}) or kind in ("new_site", "rebuild")
    if kind is None and not wants_chat:
        return {"primary": None, "secondary": None, "kind": "skip"}
    if kind is None:
        return {"primary": "chatbot", "secondary": None, "kind": "chatbot_only"}
    return {"primary": build, "secondary": "chatbot" if wants_chat else None, "kind": kind}


def _top_findings(audit: dict, n: int = 2) -> list[str]:
    fs = sorted(audit["findings"], key=lambda f: -f["points"])
    out = []
    for f in fs:
        if f["code"] in ("no_booking", "no_cta") and any(x["code"] == "no_chat" for x in fs[: n]):
            continue
        out.append(f["pitch"])
        if len(out) == n:
            break
    return out


def _svc(profile: dict, key: str) -> dict:
    return profile.get("services", {}).get(key, {})


def _price(profile: dict, key: str) -> str:
    p = _svc(profile, key).get("from_price")
    return f" Packages start from {p}." if p else ""


def _offer_paragraph(offer: dict, lead: dict, profile: dict) -> str:
    _, content, goal = CATEGORY_INFO.get(lead.get("category", ""), DEFAULT_INFO)
    paras = []
    p = offer["primary"]
    lead_in = {
        "new_site": "I can build you a proper website",
        "rebuild": "I can get you back online with a new website",
        "redesign": "I can rebuild the site",
    }.get(offer["kind"], "")
    if p == "wordpress":
        paras.append(
            f"{lead_in} on WordPress: mobile-friendly, secure (HTTPS), with {content}, and easy for you to update yourself."
            + _price(profile, "wordpress")
        )
        if "custom" in profile.get("services", {}):
            paras[-1] += " (I also hand-code custom sites if you'd like something fully tailored.)"
    elif p == "custom":
        paras.append(
            f"{lead_in} as a fast, custom-coded site (no heavy templates) that loads quickly even on mobile data, with {content}, built to turn visitors into {goal}."
            + _price(profile, "custom")
        )
        if "wordpress" in profile.get("services", {}):
            paras[-1] += " (Or on WordPress, if you'd prefer to edit everything yourself.)"
    if p == "chatbot" or offer.get("secondary") == "chatbot":
        txt = (
            "a chatbot for your website and WhatsApp that answers the usual questions (prices, availability, location, opening hours) "
            f"24/7 in English, Sinhala or Tamil, and passes real {goal} straight to you."
        )
        if p == "chatbot":
            paras.append("Your site already covers the basics, so the quickest win would be " + txt + _price(profile, "chatbot"))
        else:
            paras.append("I can also add " + txt)
    return "\n\n".join(paras)


def _subject(lead: dict, offer: dict, audit: dict) -> str:
    codes = {f["code"] for f in audit["findings"]}
    name = lead["name"]
    if codes & URGENT:
        return f"{name}: your website link isn't working"
    if offer["kind"] == "new_site":
        return f"A website for {name}?"
    if offer["kind"] == "chatbot_only":
        return f"Answering {name}'s customer questions 24/7"
    poss = name + ("'" if name.endswith("s") else "'s")
    return f"Quick idea for {poss} website"


def draft_template(lead: dict, audit: dict, profile: dict) -> dict:
    offer = choose_offer(lead, audit, profile)
    if offer["kind"] == "skip":
        return {"offer": offer, "subject": "", "email": "", "whatsapp": "", "engine": "none"}

    cat_phrase, _, _ = CATEGORY_INFO.get(lead.get("category", ""), DEFAULT_INFO)
    me = profile.get("your_name", "[Your name]")
    where = {"google": "Google Maps"}.get(lead.get("source"), "online")
    praise = ""
    if (lead.get("rating") or 0) >= 4.3 and (lead.get("reviews") or 0) >= 20:
        praise = f" (great to see {lead['rating']}★ from {lead['reviews']} reviews!)"
    finds = _top_findings(audit)
    noticed = ""
    if finds:
        noticed = "While looking, I noticed " + finds[0]
        if len(finds) > 1:
            noticed += ". Also, " + finds[1]
        noticed += "."

    hook = profile.get("offer_hook", "a free homepage mockup")
    sig = "\n".join(x for x in [
        me,
        profile.get("business_name", ""),
        " · ".join(x for x in [profile.get("whatsapp", ""), profile.get("email", "")] if x),
        profile.get("portfolio_url", ""),
    ] if x)

    email = (
        f"Hi {lead['name']} team,\n\n"
        f"I'm {me}, a web developer based in {profile.get('base_city', 'Sri Lanka')}. "
        f"I came across {lead['name']} {'on ' if where != 'online' else ''}{where} while looking at {cat_phrase} in {lead.get('city') or 'your area'}{praise}.\n\n"
        f"{noticed}\n\n"
        f"{_offer_paragraph(offer, lead, profile)}\n\n"
        f"If it's useful, I'm happy to make {hook} for {lead['name']} so you can see the idea first. No cost, no obligation.\n\n"
        f"Would you be open to a quick 10-minute call or WhatsApp chat this week?\n\n"
        f"Thanks,\n{sig}\n\n"
        f"P.S. If this isn't relevant, just reply \"no thanks\" and I won't contact you again."
    ).replace("\n\n\n\n", "\n\n")

    label = {
        "wordpress": _svc(profile, "wordpress").get("label", "WordPress websites"),
        "custom": _svc(profile, "custom").get("label", "custom-coded websites"),
        "chatbot": _svc(profile, "chatbot").get("label", "website & WhatsApp chatbots"),
    }[offer["primary"]]
    short_find = finds[0] if finds else "a few quick wins for your website"
    wa = (
        f"Hi! I'm {me}, a web developer in {profile.get('base_city', 'Sri Lanka')}. "
        f"I came across {lead['name']} and noticed {short_find}. "
        f"I help {cat_phrase} with {label}. "
        f"Happy to make {hook} for you, no obligation. Interested? "
        f"(If not, just reply \"no\" and I won't message again.)"
    )
    if profile.get("portfolio_url"):
        wa += f"\nMy work: {profile['portfolio_url']}"

    return {"offer": offer, "subject": _subject(lead, offer, audit), "email": email, "whatsapp": wa, "engine": "template"}


# ------------------------------------------------------------------ Claude mode
SYSTEM = """You write short, honest cold outreach for a Sri Lankan freelance web developer.
They offer WordPress websites, custom-coded websites, and website/WhatsApp chatbots.

Rules:
- Use ONLY the facts provided. Never invent numbers, reviews, results, clients or deadlines.
- Lead with one or two specific things noticed about THIS business's online presence, in plain words (no jargon).
- Recommend the offer given in `offer`; mention the secondary offer in one sentence at most.
- Friendly, respectful, local tone. Sri Lankan English is fine. No hype words ("revolutionize", "skyrocket").
- Email body: 90-150 words, a low-pressure call to action (free mockup / short call), sign-off with the sender details given,
  and a final line telling them to reply "no thanks" to not be contacted again.
- WhatsApp message: under 450 characters, same facts, ends with an easy opt-out.
- Subject: under 60 characters, specific to the business, not clickbait.
- Write everything in the requested language (en = English, si = Sinhala, ta = Tamil). Keep the business name as written."""

SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "email": {"type": "string"},
        "whatsapp": {"type": "string"},
    },
    "required": ["subject", "email", "whatsapp"],
    "additionalProperties": False,
}


def draft_ai(lead: dict, audit: dict, profile: dict, lang: str = "en", model: str | None = None) -> dict:
    base = draft_template(lead, audit, profile)
    if base["engine"] == "none":
        return base
    try:
        import anthropic
    except ImportError:
        base["ai_error"] = "anthropic package not installed (pip install anthropic)"
        return base

    facts = {
        "business": {k: lead.get(k) for k in ("name", "category", "city", "rating", "reviews", "source")},
        "website": lead.get("website") or "none",
        "observations": _top_findings(audit, 3),
        "platform": audit.get("platform"),
        "offer": base["offer"],
        "sender": {k: profile.get(k) for k in ("your_name", "business_name", "base_city", "whatsapp", "email", "portfolio_url")},
        "services": profile.get("services", {}),
        "free_hook": profile.get("offer_hook", "a free homepage mockup"),
        "language": lang,
        "template_draft_for_reference": base["email"],
    }
    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(
            model=model or os.environ.get("LEADAGENT_MODEL", "claude-opus-5-5"),
            max_tokens=4000,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(facts, ensure_ascii=False, indent=2)}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        base["ai_error"] = "Anthropic API key missing or invalid (set ANTHROPIC_API_KEY)"
        return base
    except anthropic.RateLimitError:
        base["ai_error"] = "rate limited by the Anthropic API; template draft kept"
        return base
    except anthropic.APIStatusError as e:
        base["ai_error"] = f"API error {e.status_code}: {e.message}"
        return base
    except anthropic.APIConnectionError:
        base["ai_error"] = "could not reach the Anthropic API; template draft kept"
        return base

    if resp.stop_reason == "refusal":
        base["ai_error"] = "model declined; template draft kept"
        return base
    text = "".join(b.text for b in resp.content if b.type == "text")
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        base["ai_error"] = "could not parse model output; template draft kept"
        return base
    base.update(subject=out["subject"], email=out["email"], whatsapp=out["whatsapp"], engine=f"ai:{resp.model}:{lang}")
    return base


def draft_followup(lead: dict, audit: dict, pitch: dict, profile: dict) -> dict:
    """A short, polite follow-up for leads you contacted a few days ago with no reply."""
    me = profile.get("your_name", "[Your name]")
    hook = profile.get("offer_hook", "a free homepage mockup")
    finds = _top_findings(audit, 1)
    reminder = f" (about how {re.split(r'[:,(]', finds[0])[0].strip()})" if finds else ""
    email = (
        f"Hi {lead['name']} team,\n\n"
        f"Just following up on my message from a few days ago{reminder}.\n\n"
        f"I know you're busy, so here's a simple option: I'll make {hook} for {lead['name']} at no cost. "
        f"If you like it, we can talk; if not, no problem at all.\n\n"
        f"Shall I go ahead?\n\n"
        f"Thanks,\n{me}\n{profile.get('whatsapp', '')}\n\n"
        f"(This is my last message unless you reply.)"
    )
    wa = (
        f"Hi, {me} again 🙂 Just checking if you saw my earlier message about {lead['name']}'s website. "
        f"Happy to make {hook}, free, no obligation. Shall I? (No reply needed if not interested, I won't message again.)"
    )
    subject = "Re: " + (pitch.get("subject") or f"{lead['name']} website")
    return {"subject": subject, "email": email, "whatsapp": wa}


def ai_prompt(lead: dict, audit: dict, draft: dict, profile: dict) -> str:
    """A ready-to-paste prompt for a free AI chat (claude.ai, etc.) to polish one draft at no API cost."""
    facts = "\n".join(f"- {f}" for f in _top_findings(audit, 3)) or "- (no specific issues)"
    offer = draft.get("offer") or {}
    return (
        "Rewrite this cold outreach for a Sri Lankan business so it sounds natural, warm and specific. "
        "Use ONLY the facts below; don't invent numbers, reviews or results. "
        "Give me: (1) an email subject under 60 characters, (2) an email body of 90–150 words, "
        "(3) a WhatsApp message under 450 characters, (4) the same WhatsApp message in Sinhala, "
        "(5) the same WhatsApp message in Tamil. Keep the opt-out line.\n\n"
        f"Business: {lead['name']} ({lead.get('category', '')}, {lead.get('city', '')})"
        + (f", Google rating {lead['rating']} from {lead.get('reviews')} reviews" if lead.get("rating") else "")
        + f"\nWebsite: {lead.get('website') or 'none'}\nWhat I noticed:\n{facts}\n"
        f"What I'm offering: {offer.get('primary')} (secondary: {offer.get('secondary') or 'none'})\n"
        f"Free hook: {profile.get('offer_hook', 'a free homepage mockup')}\n"
        f"Me: {profile.get('your_name')}, {profile.get('business_name')}, {profile.get('base_city')}, "
        f"{profile.get('whatsapp')}, {profile.get('portfolio_url')}\n\n"
        f"Current draft:\n{draft.get('email', '')}"
    )


PLACEHOLDERS = ("Your Name", "Your Studio", "you@example.com", "7X XXX XXXX", "your-portfolio.example")


def profile_problems(profile: dict) -> list[str]:
    blob = json.dumps(profile)
    return [p for p in PLACEHOLDERS if p in blob]


def whatsapp_ok(lead: dict) -> bool:
    return is_mobile(lead.get("phone"))

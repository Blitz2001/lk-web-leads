"""Offline tests: a local HTTP server stands in for real business websites."""
from __future__ import annotations

import csv
import datetime as dt
import http.server
import json
import os
import socket
import threading

import pytest

from leadagent import sources
from leadagent.checker import audit_site
from leadagent.cli import main
from leadagent.pitch import choose_offer, draft_template
from leadagent.util import normalize_lk_phone

os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
YEAR = dt.date.today().year

PAGES = {
    "/good": f"""<html><head><title>Lagoon Villa Galle</title><meta name="viewport" content="width=device-width">
      <meta name="description" content="Boutique villa"></head><body><h1>Lagoon Villa</h1>{'<p>Rooms and rates. </p>' * 40}
      <a href="tel:+94771234567">Call</a><a href="https://wa.me/94771234567">WhatsApp</a><a>Book now</a>
      <form class="wpcf7">contact</form><footer>© {YEAR} Lagoon Villa</footer></body></html>""",
    "/old": """<html><head><title>Sunrise Guest House</title><meta name="generator" content="WordPress 4.9.8">
      <script src="/wp-includes/js/jquery/jquery.js?ver=1.12.4"></script></head><body>
      <table><tr><td>Welcome to Sunrise Guest House. We have rooms with sea views and a restaurant serving Sri Lankan rice and curry.
      Contact us by phone 0912234567. Free wifi, airport pickup, tours to Yala and Mirissa whale watching are also available.</td></tr></table>
      <footer>Copyright 2016 Sunrise</footer></body></html>""",
    "/biz": """<html><head><title>Hill Cafe</title><meta name="viewport" content="width=device-width"></head><body>
      <p>Best kottu in town.</p><a href="/contact-us">Contact</a><a href="https://www.facebook.com/hillcafe?ref=x">fb</a></body></html>""",
    "/contact-us": """<html><body><p>Email: hello [at] hillcafe.lk or call 077 555 1234</p>
      <a href="https://wa.me/94775551234">WhatsApp us</a><form>message</form></body></html>""",
    "/parked": "<html><body><h1>This domain is for sale!</h1><p>Buy this domain today.</p></body></html>",
    "/soon": "<html><head><meta name='viewport' content='width=device-width'></head><body><h1>Coming soon</h1><p>Our new website is launching soon.</p></body></html>",
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGES.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write((body or "<h1>Not Found</h1>").encode())

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


PROFILE = json.load(open(os.path.join(os.path.dirname(__file__), "..", "profile.example.json")))


def codes(a):
    return {f.code for f in a.findings}


def test_phone_normalisation():
    assert normalize_lk_phone("077 123 4567") == "94771234567"
    assert normalize_lk_phone("+94 77 123 4567") == "94771234567"
    assert normalize_lk_phone("0094771234567") == "94771234567"
    assert normalize_lk_phone("011 2345678, 071 9876543") == "94719876543"  # prefers mobile
    assert normalize_lk_phone("(091) 2234567") == "94912234567"
    assert normalize_lk_phone("12345") is None


def test_no_website_and_social():
    assert "no_website" in codes(audit_site(None))
    a = audit_site("https://www.facebook.com/sunrisegh")
    assert "social_only" in codes(a) and a.tier == "hot"
    assert "dead_google_site" in codes(audit_site("https://sunrise.business.site"))
    assert "listing_only" in codes(audit_site("https://www.booking.com/hotel/lk/x.html"))


def test_good_site_is_cold(site):
    a = audit_site(site + "/good", "hotels")
    assert a.reachable and a.has_viewport and a.has_chat and a.has_booking
    assert a.tier == "cold", a.findings
    # http only (local server) is the one thing flagged
    assert codes(a) <= {"no_https"}


def test_old_site_findings(site):
    a = audit_site(site + "/old", "hotels")
    c = codes(a)
    assert a.platform == "WordPress" and a.platform_version == "4.9.8"
    assert {"not_mobile", "stale", "old_wordpress", "no_chat", "no_booking", "no_https", "no_seo_basics"} <= c
    assert a.copyright_year == 2016
    assert a.tier == "hot"


def test_parked_404_down(site):
    assert "parked" in codes(audit_site(site + "/parked"))
    assert "under_construction" in codes(audit_site(site + "/soon"))
    assert "http_error" in codes(audit_site(site + "/missing"))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    a = audit_site(f"http://127.0.0.1:{port}/", timeout=3)
    assert a.findings and a.findings[0].code in ("unreachable", "timeout")


def test_offer_logic(site):
    hotel = {"name": "Sunrise", "category": "hotels", "city": "Galle", "source": "google"}
    salon = {"name": "Glow", "category": "salons", "city": "Kandy", "source": "google"}
    none = audit_site(None).to_dict()
    assert choose_offer(hotel, none, PROFILE) == {"primary": "custom", "secondary": "chatbot", "kind": "new_site"}
    assert choose_offer(salon, none, PROFILE)["primary"] == "wordpress"
    old = audit_site(site + "/old", "hotels").to_dict()
    assert choose_offer(hotel, old, PROFILE)["primary"] == "wordpress"  # existing WP site → WP redesign
    good = audit_site(site + "/good", "hotels").to_dict()
    assert choose_offer(hotel, good, PROFILE)["kind"] == "skip"


def test_template_pitch_mentions_specifics(site):
    lead = {"name": "Sunrise Guest House", "category": "hotels", "city": "Galle", "source": "google",
            "rating": 4.6, "reviews": 212, "phone": "94771234567"}
    p = draft_template(lead, audit_site(site + "/old", "hotels").to_dict(), PROFILE)
    assert "Sunrise Guest House" in p["email"] and "Sunrise Guest House" in p["subject"]
    assert "WordPress" in p["email"] and "mobile-friendly" in p["email"]
    assert "4.6★" in p["email"]
    assert "no thanks" in p["email"] and "won't message again" in p["whatsapp"]
    assert "chatbot" in p["email"]
    assert len(p["whatsapp"]) < 700


def test_parsers():
    osm = {"elements": [
        {"type": "node", "id": 1, "lat": 6.03, "lon": 80.21, "tags": {"name": "Fort Cafe", "amenity": "cafe", "phone": "+94 77 555 1212", "website": "fortcafe.lk"}},
        {"type": "way", "id": 2, "center": {"lat": 6.0, "lon": 80.2}, "tags": {"name": "No Site Inn", "tourism": "guest_house"}},
        {"type": "node", "id": 3, "tags": {"amenity": "cafe"}},  # unnamed → dropped
    ]}
    leads = sources.parse_overpass(osm, "galle", "restaurants")
    assert [l["name"] for l in leads] == ["Fort Cafe", "No Site Inn"]
    assert leads[0]["website"] == "http://fortcafe.lk" and leads[0]["phone"] == "94775551212"
    assert leads[1]["lat"] == 6.0
    q = sources.overpass_query(6, 80, 5000, sources.CATEGORIES["hotels"][0])
    assert "around:5000,6,80" in q and 'nwr["name"]' in q

    places = {"places": [
        {"displayName": {"text": "Ella Rock View"}, "internationalPhoneNumber": "+94 76 111 2222", "rating": 4.8,
         "userRatingCount": 90, "businessStatus": "OPERATIONAL", "googleMapsUri": "https://maps.google.com/?cid=1"},
        {"displayName": {"text": "Closed Place"}, "businessStatus": "CLOSED_PERMANENTLY"},
    ]}
    g = sources.parse_places(places, "ella", "hotels")
    assert len(g) == 1 and g[0]["website"] is None and g[0]["phone"] == "94761112222"


def test_end_to_end_csv(site, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "in.csv"
    with open(f, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Name", "Category", "City", "Phone", "Website", "Email"])
        w.writerow(["Sunrise Guest House", "hotels", "Galle", "077 123 4567", site + "/old", "info@sunrise.lk"])
        w.writerow(["Lagoon Villa", "hotels", "Galle", "0771112223", site + "/good", ""])
        w.writerow(["Kandy Glow Salon", "salons", "Kandy", "081 2223334", "", ""])
        w.writerow(["Spice Hut", "restaurants", "Galle", "0712223334", "https://facebook.com/spicehut", ""])
    main(["--db", "t.db", "run", "--source", "csv", "--file", str(f), "--profile", "nope.json", "--timeout", "5"])
    html = (tmp_path / "out" / "review.html").read_text()
    rows = list(csv.DictReader(open(tmp_path / "out" / "leads.csv")))
    names = [r["name"] for r in rows]
    assert "Lagoon Villa" not in names  # good site isn't pitched
    assert set(names) == {"Sunrise Guest House", "Kandy Glow Salon", "Spice Hut"}
    assert "Sunrise Guest House" in html and "</script>" in html
    salon = next(r for r in rows if r["name"] == "Kandy Glow Salon")
    assert salon["whatsapp"] == ""  # landline, so no WhatsApp
    # mark as sent → disappears from the next report
    main(["--db", "t.db", "mark", rows[0]["id"], "sent"])
    main(["--db", "t.db", "report", "--profile", "nope.json"])
    rows2 = list(csv.DictReader(open(tmp_path / "out" / "leads.csv")))
    assert len(rows2) == 2


def test_contact_page_crawl(site):
    a = audit_site(site + "/biz", "restaurants")
    assert a.emails_found == ["hello@hillcafe.lk"]
    assert a.phones_found == ["94775551234"]
    assert a.facebook_found == "https://www.facebook.com/hillcafe"
    assert a.has_contact_form and a.has_chat is None


def test_followups_and_ai_prompt(site, tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "in.csv"
    f.write_text(f"name,category,city,website\nHill Cafe,restaurants,Kandy,{site}/biz\nOld Inn,hotels,Galle,{site}/old\n")
    main(["--db", "t.db", "run", "--source", "csv", "--file", str(f), "--profile", "nope.json", "--no-open"])
    rows = list(csv.DictReader(open(tmp_path / "out" / "leads.csv")))
    hill = next(r for r in rows if r["name"] == "Hill Cafe")
    assert hill["email"] == "hello@hillcafe.lk" and hill["whatsapp"] == "+94 77 555 1234"
    main(["--db", "t.db", "mark", hill["id"], "sent"])
    con = sqlite3.connect(tmp_path / "t.db")
    con.execute("UPDATE leads SET sent_at='2020-01-01T00:00:00' WHERE id=?", (hill["id"],)); con.commit()
    main(["--db", "t.db", "report", "--profile", "nope.json", "--no-open"])
    rows = list(csv.DictReader(open(tmp_path / "out" / "leads.csv")))
    assert rows[0]["name"] == "Hill Cafe" and rows[0]["followup_due"] == "yes"
    html = (tmp_path / "out" / "review.html").read_text()
    assert "Just following up" in html and "Copy AI prompt" in html and "Rewrite this cold outreach" in html
    main(["--db", "t.db", "mark", hill["id"], "followed_up"])
    main(["--db", "t.db", "report", "--profile", "nope.json", "--no-open"])
    rows = list(csv.DictReader(open(tmp_path / "out" / "leads.csv")))
    assert [r["name"] for r in rows] == ["Old Inn"]


def test_wizard_profile(tmp_path, monkeypatch):
    from leadagent import wizard
    monkeypatch.chdir(tmp_path)
    answers = iter(["Nimal Perera", "", "Kandy", "+94 77 000 0000", "", "https://fiverr.com/nimal", "", "LKR 40,000", "", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    wizard.setup_profile(force=True)
    p = json.loads((tmp_path / "profile.json").read_text())
    assert p["your_name"] == "Nimal Perera" and p["base_city"] == "Kandy"
    assert p["services"]["wordpress"]["from_price"] == "LKR 40,000"
    assert "from_price" not in p["services"]["custom"]
    from leadagent.pitch import profile_problems
    assert profile_problems(p) == []

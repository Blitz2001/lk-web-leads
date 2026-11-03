"""Interactive menu: run `python -m leadagent` with no arguments (or double-click start.bat / start.sh)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import sources

PROFILE = Path("profile.json")


def ask(q: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        v = input(f"{q}{hint}: ").strip()
    except EOFError:
        v = ""
    return v or default


def setup_profile(force: bool = False) -> None:
    old = json.loads(PROFILE.read_text(encoding="utf-8")) if PROFILE.exists() else {}
    if PROFILE.exists() and not force:
        return
    ex = json.loads((Path(__file__).resolve().parent.parent / "profile.example.json").read_text(encoding="utf-8"))
    base = {**ex, **old}
    print("\n── Your details (used to sign each pitch). Press Enter to keep the value in [brackets].")

    def keep(k):
        v = base.get(k, "")
        return "" if v in ("Your Name", "Your Studio", "you@example.com", "+94 7X XXX XXXX", "https://your-portfolio.example") else v

    p = dict(base)
    p["your_name"] = ask("Your name", keep("your_name"))
    p["business_name"] = ask("Business / brand name (optional)", keep("business_name"))
    p["base_city"] = ask("Your city", keep("base_city") or "Colombo")
    p["whatsapp"] = ask("Your WhatsApp number", keep("whatsapp"))
    p["email"] = ask("Your email", keep("email"))
    p["portfolio_url"] = ask("Portfolio / Fiverr / Facebook page link (very important)", keep("portfolio_url"))
    p["offer_hook"] = ask("Free thing you offer to start the chat", base.get("offer_hook", "a free homepage mockup"))
    svc = p.setdefault("services", {})
    print("Starting prices (leave blank to not mention a price):")
    for key, label in (("wordpress", "WordPress site"), ("custom", "Custom-coded site"), ("chatbot", "Chatbot")):
        s = svc.setdefault(key, {})
        prev = old.get("services", {}).get(key, {}).get("from_price", "")  # never default to the example prices
        s["from_price"] = ask(f"  {label} from (e.g. LKR 40,000)", prev)
        if not s["from_price"]:
            s.pop("from_price")
    PROFILE.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ saved {PROFILE.resolve()}\n")


def pick_categories() -> str:
    cats = list(sources.CATEGORIES)
    print("\nBusiness types:")
    for i, c in enumerate(cats, 1):
        print(f"  {i:>2}. {c:<13} {sources.CATEGORIES[c][1]}")
    raw = ask("Pick numbers (e.g. 1,2,4)", "1")
    chosen = []
    for part in raw.replace(" ", "").split(","):
        if part.isdigit() and 1 <= int(part) <= len(cats):
            chosen.append(cats[int(part) - 1])
        elif part in cats:
            chosen.append(part)
    return ",".join(chosen) or "hotels"


def menu() -> list[str] | None:
    from .cli import main

    if not PROFILE.exists():
        print("Welcome! Let's set up your profile first (takes 1 minute).")
        setup_profile(force=True)

    while True:
        print(
            "\n══ Lead Agent ══\n"
            "  1. Find new leads: OpenStreetMap (free)\n"
            "  2. Find new leads: Google Maps (needs API key, more results)\n"
            "  3. Import my own list (CSV)\n"
            "  4. Open today's review page (new leads + follow-ups due)\n"
            "  5. Check one website\n"
            "  6. Pipeline stats\n"
            "  7. Edit my profile\n"
            "  8. Health check (internet, settings)\n"
            "  0. Exit"
        )
        choice = ask("Choose", "1")
        try:
            if choice in ("1", "2"):
                if choice == "2" and not os.environ.get("GOOGLE_MAPS_API_KEY"):
                    print("! GOOGLE_MAPS_API_KEY isn't set. See GUIDE.md section 'Google Maps (optional)'.")
                    continue
                print("\nTowns: any Sri Lankan town works, e.g. Galle, Kandy, Negombo, Ella, Jaffna, Kurunegala")
                city = ask("Town(s), comma-separated", "Galle")
                cats = pick_categories()
                limit = ask("Max leads per town & type", "30")
                ps = ask("Also run Google PageSpeed test? slower, free (y/N)", "n").lower().startswith("y")
                args = ["run", "--source", "osm" if choice == "1" else "google", "--city", city, "--category", cats, "--limit", limit]
                sh = ask("Save phone screenshots of weak sites? free, needs playwright (y/N)", "n").lower().startswith("y")
                main(args + (["--pagespeed"] if ps else []) + (["--screenshots"] if sh else []))
            elif choice == "3":
                f = ask("Path to CSV file", "my_leads.csv")
                main(["run", "--source", "csv", "--file", f])
            elif choice == "4":
                top = ask("How many new leads to show today (0 = all)", "15")
                main(["report", "--top", top])
            elif choice == "5":
                main(["check", ask("Website URL")])
            elif choice == "6":
                main(["stats"])
            elif choice == "7":
                setup_profile(force=True)
            elif choice == "8":
                main(["doctor"])
            elif choice == "0":
                return None
        except SystemExit as e:
            if e.code not in (0, None):
                print(f"! {e.code}")

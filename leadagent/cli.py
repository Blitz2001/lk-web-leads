"""Command line entry point: python -m leadagent <command> ..."""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import sources
from .checker import audit_site
from .db import STATUSES, Store
from .pitch import draft_ai, draft_template, profile_problems
from .report import write_outputs

def load_profile(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        ex = Path(__file__).resolve().parent.parent / "profile.example.json"
        print(f"! {path} not found, using {ex.name}. Copy it to profile.json and fill in your details.", file=sys.stderr)
        p = ex
    return json.loads(p.read_text(encoding="utf-8"))


def cmd_find(args, store: Store) -> list[str]:
    ids: list[str] = []
    cats = [c.strip() for c in args.category.split(",")] if args.category else ["other"]
    cities = [c.strip() for c in args.city.split(",")] if args.city else [""]
    for city in cities:
        for cat in cats:
            if args.source != "csv" and cat not in sources.CATEGORIES:
                raise SystemExit(f"Unknown category '{cat}'. Choose from: {', '.join(sources.CATEGORIES)}")
            if args.source == "osm":
                leads = sources.from_osm(city, cat, radius_km=args.radius, limit=args.limit)
            elif args.source == "google":
                leads = sources.from_google(city, cat, limit=args.limit, query=args.query)
            else:
                if not args.file:
                    raise SystemExit("--source csv needs --file leads.csv")
                leads = sources.from_csv(args.file, default_city=city, default_category=cat)
            new = sum(store.upsert_lead(l) for l in leads)
            ids += [l["id"] for l in leads]
            where = f"{cat} in {city}" if args.source != "csv" else f"rows from {args.file}"
            print(f"· {args.source}: {len(leads)} {where} ({new} new)")
            if args.source == "osm":
                time.sleep(1)
    return ids


def cmd_audit(args, store: Store, only: set[str] | None = None) -> None:
    todo = [r for r in store.all()
            if (only is None or r["id"] in only)
            and r["status"] in ("new", "reviewed")
            and (args.refresh or r["audit"] is None)]
    if not todo:
        print("· nothing to audit")
        return
    print(f"· auditing {len(todo)} websites…")
    done: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(audit_site, r["lead"].get("website"), r["lead"].get("category", ""), args.timeout,
                          getattr(args, "pagespeed", False)): r for r in todo}
        for i, f in enumerate(as_completed(futs), 1):
            r = futs[f]
            try:
                a = f.result().to_dict()
            except Exception as e:  # one bad site must not stop the batch
                print(f"  ! {r['lead']['name']}: {e}")
                continue
            store.set_audit(r["id"], a)
            done[r["id"]] = a
            print(f"  [{i}/{len(todo)}] {a['score']:>3} {a['tier']:<4} {r['lead']['name'][:50]}")
    if getattr(args, "screenshots", False):
        from .shots import capture
        targets = [(lid, a["final_url"]) for lid, a in done.items() if a.get("reachable") and a["score"] >= 25]
        if targets:
            print(f"· taking {len(targets)} phone screenshots…")
            for lid, rel in capture(targets, getattr(args, "out", "out")).items():
                store.set_audit(lid, {**done[lid], "screenshot": rel})


def cmd_pitch(args, store: Store, only: set[str] | None = None) -> None:
    profile = load_profile(args.profile)
    bad = profile_problems(profile)
    if bad:
        print(f"! profile.json still has placeholder values ({', '.join(bad)}). "
              "Run `python -m leadagent setup` so your pitches are signed properly.")
    n = 0
    for r in store.all():
        if r["audit"] is None or r["status"] not in ("new", "reviewed"):
            continue
        if only is not None and r["id"] not in only:
            continue
        if r["pitch"] and not args.redraft:
            continue
        if r["audit"]["score"] < args.min_score:
            continue
        if args.ai:
            p = draft_ai(r["lead"], r["audit"], profile, lang=args.lang, model=args.model)
            if p.get("ai_error"):
                print(f"  ! {r['lead']['name']}: {p['ai_error']}")
        else:
            p = draft_template(r["lead"], r["audit"], profile)
        store.set_pitch(r["id"], p)
        n += 1
    print(f"· drafted {n} pitches")


def cmd_report(args, store: Store) -> None:
    profile = load_profile(args.profile)
    h, c, n = write_outputs(store.all(), args.out, profile, min_score=args.min_score, include_done=args.all,
                            followup_days=args.followup_days, top=args.top)
    print(f"· {n} leads ready for review\n  open: {h.resolve()}\n  csv:  {c.resolve()}")
    if not args.no_open and sys.stdout.isatty():
        import webbrowser
        webbrowser.open(h.resolve().as_uri())


def cmd_doctor(args) -> None:
    import platform

    import requests

    ok = True
    print(f"Python {platform.python_version()} {'✓' if sys.version_info >= (3, 10) else '✗ need 3.10+'}")
    try:
        import bs4  # noqa: F401
        print("packages ✓")
    except ImportError:
        ok = False
        print("✗ missing packages: run  pip install -r requirements.txt")
    prof = Path(args.profile)
    if not prof.exists():
        ok = False
        print("✗ no profile.json: run  python -m leadagent setup")
    else:
        bad = profile_problems(json.loads(prof.read_text(encoding="utf-8")))
        print("profile ✓" if not bad else f"✗ profile has placeholders: {', '.join(bad)}")
    import os
    for name, url in [("OpenStreetMap", "https://overpass-api.de/api/status"),
                      ("Town lookup", "https://nominatim.openstreetmap.org/status"),
                      ("Google PageSpeed", "https://www.googleapis.com/pagespeedonline/v5/runPagespeed")]:
        try:
            requests.get(url, timeout=10)
            print(f"{name} reachable ✓")
        except requests.RequestException:
            ok = False
            print(f"✗ can't reach {name}: check your internet")
    print("Google Maps key:", "set ✓" if os.environ.get("GOOGLE_MAPS_API_KEY") else "not set (optional)")
    print("Anthropic key:  ", "set ✓" if os.environ.get("ANTHROPIC_API_KEY") else "not set (optional, use the free 'Copy AI prompt' button instead)")
    print("\nAll good! Run  python -m leadagent" if ok else "\nFix the ✗ items above, then run again.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="leadagent", description="Find Sri Lankan businesses with weak websites and draft pitches you send yourself.")
    ap.add_argument("--db", default="leads.db")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common_find(p):
        p.add_argument("--source", choices=["osm", "google", "csv"], default="osm")
        p.add_argument("--city", help="comma-separated, e.g. 'Galle,Unawatuna'")
        p.add_argument("--category", help=f"comma-separated: {', '.join(sources.CATEGORIES)}")
        p.add_argument("--query", help="custom Google search phrase, e.g. 'ayurveda spa'")
        p.add_argument("--file", help="CSV file for --source csv")
        p.add_argument("--radius", type=float, default=5, help="km around the city centre (OSM)")
        p.add_argument("--limit", type=int, default=40)

    def common_audit(p):
        p.add_argument("--workers", type=int, default=6)
        p.add_argument("--timeout", type=float, default=20)
        p.add_argument("--refresh", action="store_true", help="re-audit sites already checked")
        p.add_argument("--pagespeed", action="store_true", help="also get Google's free PageSpeed mobile score (slower)")
        p.add_argument("--screenshots", action="store_true", help="save a phone-view screenshot of each weak site (needs playwright)")

    def common_pitch(p):
        p.add_argument("--profile", default="profile.json")
        p.add_argument("--min-score", type=int, default=25, help="only pitch leads at or above this score")
        p.add_argument("--ai", action="store_true", help="polish drafts with Claude (needs ANTHROPIC_API_KEY)")
        p.add_argument("--lang", choices=["en", "si", "ta"], default="en", help="draft language for --ai")
        p.add_argument("--model", help="override Claude model id")
        p.add_argument("--redraft", action="store_true")

    def common_report(p):
        p.add_argument("--out", default="out")
        p.add_argument("--all", action="store_true", help="include sent/skipped leads")
        p.add_argument("--top", type=int, default=0, help="show only the best N new leads (a day's batch)")
        p.add_argument("--followup-days", type=int, default=4, help="show a follow-up for leads sent this many days ago")
        p.add_argument("--no-open", action="store_true", help="don't open the page in the browser")

    p = sub.add_parser("run", help="find → audit → pitch → report in one go")
    common_find(p); common_audit(p); common_pitch(p); common_report(p)
    p = sub.add_parser("find", help="collect leads"); common_find(p)
    p = sub.add_parser("audit", help="check websites"); common_audit(p)
    p = sub.add_parser("pitch", help="draft messages"); common_pitch(p)
    p = sub.add_parser("report", help="write out/review.html and out/leads.csv")
    p.add_argument("--profile", default="profile.json"); p.add_argument("--min-score", type=int, default=0); common_report(p)
    p = sub.add_parser("mark", help="update a lead's status after you contact them")
    p.add_argument("id", help="lead id (prefix ok)"); p.add_argument("status", choices=STATUSES); p.add_argument("--note")
    p = sub.add_parser("import-status", help="apply statuses exported from review.html")
    p.add_argument("file")
    p = sub.add_parser("stats", help="pipeline summary")
    p = sub.add_parser("check", help="audit one URL and print findings")
    p.add_argument("url"); p.add_argument("--category", default=""); p.add_argument("--pagespeed", action="store_true")
    p = sub.add_parser("setup", help="create or edit profile.json interactively")
    p = sub.add_parser("doctor", help="check internet, packages and settings")
    p.add_argument("--profile", default="profile.json")
    p = sub.add_parser("menu", help="interactive menu (same as running with no arguments)")

    if argv is None and len(sys.argv) == 1:
        argv = ["menu"]
    args = ap.parse_args(argv)
    try:
        _dispatch(args)
    except KeyboardInterrupt:
        print("\n· stopped. Everything found so far is saved; run again to continue.")
    except RuntimeError as e:
        raise SystemExit(f"! {e}")


def _dispatch(args) -> None:
    if args.cmd == "menu":
        from .wizard import menu
        menu()
        return
    if args.cmd == "setup":
        from .wizard import setup_profile
        setup_profile(force=True)
        return
    if args.cmd == "doctor":
        cmd_doctor(args)
        return

    if args.cmd == "check":
        a = audit_site(args.url, args.category, pagespeed=args.pagespeed)
        print(f"score {a.score} ({a.tier}) · platform {a.platform or '?'} · {a.load_seconds}s · status {a.status} {a.error or ''}")
        for f in sorted(a.findings, key=lambda f: -f.points):
            print(f"  +{f.points:<3} [{f.offer}] {f.pitch}")
        if a.emails_found or a.phones_found:
            print(f"  contacts found: {', '.join(a.emails_found + a.phones_found)}")
        return

    store = Store(args.db)
    if args.cmd == "run":
        ids = set(cmd_find(args, store))
        cmd_audit(args, store, only=ids)
        cmd_pitch(args, store, only=ids)
        cmd_report(args, store)
    elif args.cmd == "find":
        cmd_find(args, store)
    elif args.cmd == "audit":
        cmd_audit(args, store)
    elif args.cmd == "pitch":
        cmd_pitch(args, store)
    elif args.cmd == "report":
        cmd_report(args, store)
    elif args.cmd == "mark":
        ok = store.set_status(args.id, args.status, args.note)
        print("· updated" if ok else "! no lead with that id")
    elif args.cmd == "import-status":
        data = json.loads(Path(args.file).read_text())
        n = sum(store.set_status(i, v["status"]) for i, v in data.items() if v.get("status") in STATUSES)
        print(f"· updated {n} leads")
    elif args.cmd == "stats":
        from collections import Counter
        rs = store.all()
        print(f"{len(rs)} leads")
        print("status:", dict(Counter(r["status"] for r in rs)))
        print("tier:  ", dict(Counter(r["audit"]["tier"] for r in rs if r["audit"])))
        print("offer: ", dict(Counter((r["pitch"] or {}).get("offer", {}).get("kind", "-") for r in rs if r["pitch"])))


if __name__ == "__main__":
    main()

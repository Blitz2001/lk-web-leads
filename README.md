# Lead Agent (Sri Lanka)

Finds local Sri Lankan businesses with no website or a weak one, checks their sites, and drafts a personalised pitch for each one. The pitch offers a **WordPress site**, a **custom-coded site**, or a **website/WhatsApp chatbot**. **Nothing is sent automatically.** You review each draft in a browser page, edit it, and send it yourself by email or WhatsApp.

```
find leads  →  audit websites  →  score 0–100  →  draft pitch  →  review.html  →  you send  →  mark status
(OSM / Google / CSV)                             (template or Claude)
```

📘 **New here? Read [GUIDE.md](GUIDE.md)**: daily routine, free lead sources, free AI polishing, and how to get replies.

## Quick start (no commands needed)

- **Windows:** double-click `start.bat`
- **Mac/Linux:** run `./start.sh`

The first run installs what it needs and asks for your details. After that you get a menu:

```
1. Find new leads: OpenStreetMap (free)       5. Check one website
2. Find new leads: Google Maps (API key)      6. Pipeline stats
3. Import my own list (CSV)                   7. Edit my profile
4. Open today's review page                   8. Health check
```

Any Sri Lankan town works; unknown towns are looked up for free on OpenStreetMap.

## What's free and what's not

| Feature | Cost |
|---|---|
| OpenStreetMap leads, CSV import, website audit, contact-page finder, template drafts, review page, follow-ups | Free |
| Google PageSpeed score (`--pagespeed`) | Free |
| Phone screenshots of prospects' sites (`--screenshots`, needs `pip install playwright` + Chrome) | Free |
| **Copy AI prompt** button: paste into the free claude.ai to polish or translate to Sinhala/Tamil | Free |
| Google Places leads (`--source google`) | Monthly free allowance, card required |
| Automatic Claude drafts (`--ai`) | Paid API |

## Manual setup (optional)

```bash
cd lead-agent
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m leadagent setup                              # creates profile.json
python -m leadagent doctor                             # checks internet + settings
```

## Commands

```bash
# Free source: OpenStreetMap, no key needed
python -m leadagent run --city Galle,Unawatuna --category hotels,restaurants

# Better coverage: Google Places (enable "Places API (New)" in Google Cloud)
export GOOGLE_MAPS_API_KEY=...
python -m leadagent run --source google --city Kandy --category salons,clinics --limit 60
python -m leadagent run --source google --city Colombo --category other --query "ayurveda spa"

# Your own list, from Facebook, directories or referrals
python -m leadagent run --source csv --file my_leads.csv
```

Then open **`out/review.html`** in your browser. Each lead card shows:
- the score and tier (hot ≥ 50, warm 25–49, cold < 25), with the specific problems found
- which offer to lead with and why
- an editable email draft and WhatsApp draft, with **Copy**, **Open in email** and **Open in WhatsApp** (opens `wa.me` with the text filled in; it only appears for 07x mobile numbers)
- a status dropdown (new / reviewed / sent / replied / won / lost / skip)

Useful flags: `--top 15` (a day's batch, contactable leads first), `--pagespeed`, `--screenshots`, `--followup-days 4`, `--no-open`.

Leads marked **sent** come back automatically with a short **follow-up draft** after 4 days with no reply. Mark them `followed_up` after sending.

After you send, record the status so the lead won't appear again:

```bash
python -m leadagent mark e3d813e02a sent
# or click "Export statuses" in the page, then:
python -m leadagent import-status ~/Downloads/statuses.json
python -m leadagent stats
```

**Categories:** `hotels restaurants clinics salons tours gyms education retail auto realestate professional`
**Cities:** about 35 built in (Colombo suburbs, Kandy, Galle, Negombo, Ella, Jaffna and more). Add others in `CITIES` in `leadagent/sources.py`.

**CSV columns** (header row, any order, only `name` required): `name, category, city, address, phone, email, website, facebook, maps_url, rating, reviews`

## Claude-written drafts (optional)

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...
python -m leadagent pitch --ai --redraft              # English
python -m leadagent pitch --ai --redraft --lang si    # Sinhala   (ta = Tamil)
python -m leadagent report
```

Claude only gets the facts the audit found, so it can't invent claims. If the API fails, the template draft is kept. The default model is `claude-opus-5-5`. Override it with `--model` or `LEADAGENT_MODEL`.

## What the audit checks

| Finding | Points | Leads to |
|---|---|---|
| No website, or the link goes to Facebook, Instagram or Booking.com | 45–60 | new site |
| Dead domain, error page, parked/expired domain, dead `business.site` link | 45–55 | rebuild (urgent) |
| "Coming soon" / under construction | 45 | rebuild |
| Not mobile-friendly (no viewport) | 20 | redesign |
| No HTTPS ("Not secure") | 15 | redesign |
| Outdated WordPress (< 6.0) | 15 | WordPress redesign/fix |
| Free subdomain (wixsite, blogspot…) | 15 | new site on own domain |
| Frames, Flash or marquee | 15 | custom rebuild |
| Slow (> 4 s), heavy page, Wix/Weebly/Blogger | 5–10 | custom rebuild |
| © year 3+ years old | 10 | redesign |
| No chat/WhatsApp widget, no booking, no contact option | 10 each | chatbot |

**How the offer is chosen:** a site that's already on WordPress gets a WordPress pitch. A slow site or one on a weak builder gets a custom-coded pitch. With no site at all, hotels, tours and real estate get custom-coded first (set this in `custom_first_categories` in `profile.json`) and everyone else gets WordPress first. Each pitch mentions the other option in one line. A decent site with no chat gets a chatbot-only pitch. A good site is skipped.

Test a single site:

```bash
python -m leadagent check https://example.lk --category hotels
```

## Sending responsibly

- Send each message yourself, a handful a day, not in bulk. WhatsApp bans numbers that mass-message strangers.
- Every draft ends with an opt-out line. If someone opts out, mark them `skip`.
- Sri Lanka's Personal Data Protection Act (No. 9 of 2022) covers personal data. Use public business contact details, keep `leads.db` private, and delete leads you won't pursue.
- The audit fetches each homepage once, with a clear user agent and a short timeout.

## Tests

```bash
pip install pytest && python -m pytest -q
```

The tests run offline against a local mock web server. They cover phone parsing, the audit rules, offer selection, the pitch text, the OSM and Google parsers, and a full CSV → report → mark run.

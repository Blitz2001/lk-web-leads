# Lead Agent Playbook

How to use the tool, how to get the best results **without spending money**, and what to improve next.

---

## 1. First-time setup (10 minutes, free)

1. Install **Python 3.10+** from python.org. On Windows, tick *"Add Python to PATH"* during install.
2. Copy the `lead-agent` folder to your computer.
3. Start it:
   - **Windows:** double-click `start.bat`
   - **Mac/Linux:** open a terminal in the folder and run `./start.sh`

   The first run installs everything it needs, then asks for your details: name, WhatsApp, email, **portfolio link**, and your starting prices.
4. In the menu, choose **8. Health check**. Every line should show ✓ (the two API keys are optional).

> No portfolio yet? Build one before anything else. See section 4.

---

## 2. Daily routine (about 45 minutes a day)

| When (SLST) | What | Menu option |
|---|---|---|
| **Monday** | Find about 50–100 new leads: 2–3 towns × 2–3 business types | 1 |
| **Every weekday 09:30** | Open today's review page with **15 leads** | 4 |
| 09:30–10:30 | For each lead: read the findings, check their Facebook ("google them" link), make one personal edit, and send | in the page |
| After each send | Set the dropdown to **sent** (or **skip** if it's not a fit) | in the page |
| **Friday** | Click **Export statuses**, then run `python -m leadagent import-status statuses.json` | — |

**Follow-ups appear on their own.** If a lead you marked **sent** hasn't replied after 4 days, it comes back at the top of the review page with a short follow-up draft. Send it once, then mark it **followed_up**. Never follow up more than once.

> **Why mark statuses?** It keeps you from messaging someone twice, and it shows you which approach gets replies.

---

## 3. Getting the best results without spending money

### 3.1 Free lead sources, from best to worst

| Source | Cost | How |
|---|---|---|
| **OpenStreetMap** (built in) | Free | Menu 1. Patchy in small towns, but good for tourist areas: Galle, Ella, Mirissa, Kandy, Negombo, Sigiriya. |
| **Google Maps by hand + CSV** | Free | Search *"guest house Ella"* on Google Maps. Any business **without a "Website" button** is a lead. Copy the name, phone and town into a spreadsheet, save it as CSV, and use menu 3. 20 minutes gets you about 40 strong leads. |
| **Booking.com / Tripadvisor / Agoda** | Free | Hotels listed there with no website of their own lose 15–18% commission on every booking. Add their listing URL as the `website`; the tool recognises listing-only leads and pitches "direct bookings". |
| **Facebook pages & groups** | Free | Search "salon Kandy", "tuition class Kurunegala". A page with no website link is a lead. Put the page URL in the `website` column. |
| **ikman.lk / Yellow Pages / Rainbow Pages** | Free | Businesses that advertise but have no site are already spending on marketing, so they're good leads. |
| **Google Places API** | Card needed | Google gives a monthly free allowance, but you must add a billing card. If you try it, open *Google Cloud → APIs → Places API (New) → Quotas* and cap the daily requests so you can't be charged. Optional: the free sources above are enough. |

CSV header: `name,category,city,phone,website,email` (only `name` is required).

### 3.2 Free AI polishing (instead of the paid API)

Every lead card has a **Copy AI prompt** button. Click it, paste into the **free plan of claude.ai**, and you get:
- a polished subject, email and WhatsApp message
- **Sinhala and Tamil versions** of the WhatsApp message

Many owners outside Colombo reply far more to a message in their own language. Use this for every **hot** lead; for warm leads, the template draft is fine.

### 3.3 Free extras that raise reply rates

| Extra | How | Why it works |
|---|---|---|
| **Phone screenshot of their site** | Install once: `pip install playwright` (it uses your installed Chrome). Then tick screenshots, or run `python -m leadagent run ... --screenshots` | Owners believe a picture of *their own* site looking broken far more than any description. Attach it to the WhatsApp message. |
| **Google PageSpeed score** | Answer **y** to the PageSpeed question, or add `--pagespeed` | "Google itself scores your site 23/100 on mobile" is a hard fact they can't argue with. |
| **Free mockup** | Ask claude.ai (free): *"Make a single-page HTML homepage mockup for a guest house called X in Ella with rooms, gallery, WhatsApp button."* Host it free on Netlify Drop (drag and drop) or GitHub Pages. For WordPress demos, use **WordPress Playground** (playground.wordpress.net), a free WordPress in the browser. | Only make mockups for people who said "yes, show me". That's the hook in every pitch. |
| **Contact finder** | Built in: the tool reads each site's contact page for email, WhatsApp and Facebook. For leads with none, click **google them**. | No contact means no sale. Finding one gets you a lead others skipped. |

### 3.4 Sending, all free

- **WhatsApp Business app** (free): set your business profile, a catalogue of your three services with prices, quick replies, and labels (*New lead / Interested / Quote sent / Won*).
- **Send by hand**: 10–15 new messages a day at most. Unofficial bulk tools get numbers banned.
- **Email**: send from Gmail (free). A domain email looks better if you already have one. Keep it under about 30 cold emails a day per inbox.
- **Best times (SLST)**: Tue–Thu, **10:00–11:30** or **15:00–16:30**. Avoid Poya days and Sunday mornings. For hotels, avoid check-in and check-out rushes (12:00–14:00).

### 3.5 Writing tips that matter more than the tool

1. **One personal line on top.** Look at their Facebook or reviews and mention one real thing ("Saw your new rooftop rooms on Facebook, they look great"). This roughly doubles replies.
2. **Lead with their loss, not your skills.** "Guests can't book you directly, so you pay Booking.com commission" beats "I build modern websites".
3. **One question at the end**, easy to answer: *"Shall I make a free mockup?"*
4. **Send a voice note** after they reply. Sri Lankan owners trust a voice far more than text.
5. **Keep the opt-out line.** It's polite, and it keeps you on the right side of Sri Lanka's data protection law (PDPA, Act No. 9 of 2022).

### 3.6 Which leads to focus on (best value per message)

| Niche | Why | Best offer |
|---|---|---|
| Guest houses & villas (Ella, Galle, Mirissa, Sigiriya, Kandy) | Lose commission to Booking.com; foreign guests search Google | Custom-coded or WordPress site with direct booking + WhatsApp chatbot |
| Tour operators / drivers | Compete for foreign tourists; enquiries come at night (time zones) | Site + **24/7 chatbot** (strong selling point) |
| Dental / medical channelling centres | Phone lines are busy; patients want times | WordPress site + appointment chatbot |
| Tuition institutes | Parents ask the same questions all day | Chatbot for timetables and fees, in Sinhala/Tamil |
| Salons & bridal | Instagram-heavy, no booking | WordPress with gallery + booking |

Start with **one niche in two towns** for two weeks. Reuse the same mockup with different names. That's the fastest way to your first 3 clients.

---

## 4. Build proof first (free)

A pitch with a portfolio link gets several times more replies than one without.

1. Build **3 demo sites**: a guest house (custom-coded), a restaurant (WordPress), and a chatbot demo. Use made-up names.
2. Host them free: Netlify / Vercel / GitHub Pages for coded sites; WordPress Playground or a free InfinityFree host for the WordPress demo.
3. Make a one-page portfolio linking all three, plus your Fiverr profile.
4. Put that link in your profile (menu 7). It goes into every pitch.
5. After each client, ask for a Google review and a one-line testimonial, then add it to the portfolio.

---

## 5. Track what works

Run **menu 6 (stats)** every Friday and watch three numbers:

- **Reply rate** = (replied + won) ÷ sent. Below 5%: improve the personal line and the screenshot. 10% or more is good.
- **Win rate** = won ÷ replied. Low: improve the mockup, the speed of your reply, and your prices.
- **Best niche & town**: put more effort where wins come from.

Try one change at a time for a week (for example the subject line, a Sinhala WhatsApp message, or a screenshot vs no screenshot) and compare.

---

## 6. Common problems

| Problem | Fix |
|---|---|
| "OpenStreetMap search failed: server busy" | The free server is busy. Wait a minute and retry, or try a smaller radius or a different town. |
| Very few leads in a town | OSM is thin there. Use the Google Maps → CSV method (3.1). |
| Lead shows "no contact yet" | Click **google them**: check their Google listing or Facebook page. Add the number to your CSV and re-import. |
| Pitch says "Your Name" | Run menu 7 (Edit my profile). |
| "Open in WhatsApp" is greyed out | Their number is a landline (011, 081…). Call them, or find their mobile on Facebook. |
| Screenshots don't work | Install Google Chrome, then `pip install playwright`. |
| Want to start over | Delete `leads.db` (this loses all statuses) or move it to a backup folder. |

---

## 7. Ideas to improve the tool (ask Claude to build any of these)

**Quick wins**
- **Sinhala & Tamil templates offline**, so translated drafts don't need an AI.
- **Reply logging**: a "replied" button that records what they said, to learn which pitches work.
- **More towns and niches**: add your target areas to `CITIES` / `CATEGORIES` in `leadagent/sources.py`.

**Bigger features**
- **Auto mockup generator**: create a one-page demo site with the lead's name, photos placeholder and WhatsApp number, ready to host.
- **Google Sheets sync**: a shared sheet as your CRM, free with a Google account.
- **Gmail drafts**: push each email into your Gmail Drafts folder (free Gmail API). You still press Send.
- **Website "before/after" PDF report**: a one-page audit with their screenshot and PageSpeed score, as a professional attachment.
- **Scheduled weekly run**: automatically find new leads every Monday 08:00 SLST and have the review page ready.

**Business ideas built on the same data**
- **Monthly care plans** (LKR 3,000–8,000/month): updates, backups, security for the many outdated WordPress sites the tool finds. This is recurring income.
- **Google Business Profile setup** as a cheap entry offer for no-website leads, then upsell a site.
- **Hotel-booking chatbot package** sold to many guest houses at once: build once, customise per client.

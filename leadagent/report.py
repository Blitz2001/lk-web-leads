"""Outputs: an HTML review queue (open in your browser) and a CSV."""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
from pathlib import Path

from urllib.parse import quote_plus

from .pitch import ai_prompt, draft_followup
from .util import is_mobile, pretty_phone


def _contacts(l: dict, a: dict) -> tuple[str | None, str | None, str | None]:
    """Best email, display phone and WhatsApp number, using the website's contact page as a fallback."""
    phones = [x for x in [l.get("phone"), *a.get("phones_found", [])] if x]
    wa = next((x for x in phones if is_mobile(x)), None)
    email = l.get("email") or (a.get("emails_found") or [None])[0]
    return email, (phones[0] if phones else None), wa


def _rows(records: list[dict], min_score: int, include_done: bool, followup_days: int, top: int) -> list[dict]:
    fresh, due = [], []
    now = dt.datetime.now()
    for r in records:
        a, p = r["audit"], r["pitch"]
        if not a or not p or p.get("engine") == "none":
            continue
        if r["status"] == "sent" and r.get("sent_at"):
            try:
                age = (now - dt.datetime.fromisoformat(r["sent_at"])).days
            except ValueError:
                age = 0
            if age >= followup_days:
                due.append({**r, "followup": True})
                continue
        if a["score"] < min_score:
            continue
        if not include_done and r["status"] in ("sent", "followed_up", "replied", "won", "lost", "skip"):
            continue
        fresh.append({**r, "followup": False})
    # contactable leads first, then by score
    fresh.sort(key=lambda r: (_contacts(r["lead"], r["audit"])[2] is None and _contacts(r["lead"], r["audit"])[0] is None,
                              -r["audit"]["score"]))
    if top:
        fresh = fresh[:top]
    return due + fresh


def write_csv(records: list[dict], path: Path) -> None:
    cols = ["id", "status", "followup_due", "score", "tier", "name", "category", "city", "phone", "whatsapp", "email",
            "website", "facebook", "platform", "offer", "top_issue", "subject", "email_body", "whatsapp_msg", "maps_url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in records:
            l, a, p = r["lead"], r["audit"] or {}, r["pitch"] or {}
            fs = sorted(a.get("findings", []), key=lambda x: -x["points"])
            offer = p.get("offer") or {}
            email, phone, wa = _contacts(l, a)
            w.writerow([
                r["id"], r["status"], "yes" if r.get("followup") else "", a.get("score", ""), a.get("tier", ""),
                l["name"], l.get("category", ""), l.get("city", ""), pretty_phone(phone), pretty_phone(wa),
                email or "", l.get("website") or "", l.get("facebook") or a.get("facebook_found") or "",
                a.get("platform") or "", "+".join(x for x in [offer.get("primary"), offer.get("secondary")] if x),
                fs[0]["code"] if fs else "", p.get("subject", ""), p.get("email", ""), p.get("whatsapp", ""),
                l.get("maps_url") or "",
            ])


def write_html(records: list[dict], path: Path, profile: dict) -> None:
    items = []
    for r in records:
        l, a, p = r["lead"], r["audit"], r["pitch"]
        email, phone, wa = _contacts(l, a)
        d = draft_followup(l, a, p, profile) if r.get("followup") else {"subject": p["subject"], "email": p["email"], "whatsapp": p["whatsapp"]}
        items.append({
            "id": r["id"], "status": r["status"], "followup": bool(r.get("followup")),
            "name": l["name"], "category": l.get("category", ""), "city": l.get("city", ""),
            "phone": pretty_phone(phone), "wa": wa, "email": email, "website": l.get("website"),
            "facebook": l.get("facebook") or a.get("facebook_found"), "maps": l.get("maps_url"),
            "google": "https://www.google.com/search?q=" + quote_plus(f"{l['name']} {l.get('city', '')} Sri Lanka"),
            "rating": l.get("rating"), "reviews": l.get("reviews"),
            "score": a["score"], "tier": a["tier"], "platform": a.get("platform"),
            "load": a.get("load_seconds"), "psi": a.get("pagespeed_mobile"), "shot": a.get("screenshot"),
            "findings": [{"t": f["pitch"], "p": f["points"], "o": f["offer"]} for f in sorted(a["findings"], key=lambda x: -x["points"])],
            "offer": p["offer"], "subject": d["subject"], "emailBody": d["email"], "waMsg": d["whatsapp"],
            "engine": "follow-up" if r.get("followup") else p.get("engine"),
            "aiPrompt": ai_prompt(l, a, p, profile),
        })
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    page = TEMPLATE.replace("__DATA__", data).replace("__GENERATED__", html.escape(generated))
    path.write_text(page, encoding="utf-8")


def write_outputs(records: list[dict], out_dir: str, profile: dict, min_score: int = 0, include_done: bool = False,
                  followup_days: int = 4, top: int = 0) -> tuple[Path, Path, int]:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    rows = _rows(records, min_score, include_done, followup_days, top)
    h, c = d / "review.html", d / "leads.csv"
    write_html(rows, h, profile)
    write_csv(rows, c)
    return h, c, len(rows)


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lead Review Queue</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1b;--mute:#6b6a65;--line:#e4e2dc;--accent:#0f6e5c;--hot:#c2410c;--warm:#b7791f;--cold:#5b6b7a;--chip:#efede7}
@media (prefers-color-scheme:dark){:root{--bg:#141412;--card:#1d1d1a;--ink:#ecebe6;--mute:#a09e96;--line:#33322e;--accent:#4fc1a6;--hot:#fb923c;--warm:#f2c14e;--cold:#93a4b5;--chip:#2a2926}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:14px 16px}
.wrap{max-width:980px;margin:0 auto}h1{font-size:19px;margin:0 0 2px}.sub{color:var(--mute);font-size:13px}
.bar{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}.bar input,.bar select{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
.bar input{flex:1;min-width:160px}main{padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px}
.top{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}
.name{font-weight:650;font-size:17px}.meta{color:var(--mute);font-size:13px}.meta a{color:var(--accent)}
.score{font-weight:700;font-size:13px;padding:3px 10px;border-radius:99px;color:#fff;white-space:nowrap}
.hot{background:var(--hot)}.warm{background:var(--warm)}.cold{background:var(--cold)}
ul{margin:10px 0 4px;padding-left:18px}li{margin:2px 0}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.chip{background:var(--chip);border-radius:6px;padding:2px 8px;font-size:12px}
.tabs{display:flex;gap:4px;margin-top:10px}.tabs button{font:inherit;font-size:13px;border:1px solid var(--line);background:none;color:var(--ink);border-radius:8px 8px 0 0;padding:5px 12px;cursor:pointer}
.tabs button.on{background:var(--chip);font-weight:600}
input.subj{width:100%;font:inherit;padding:8px;border:1px solid var(--line);border-bottom:none;background:var(--card);color:var(--ink)}
textarea{width:100%;min-height:220px;font:14px/1.5 inherit;font-family:inherit;padding:10px;border:1px solid var(--line);border-radius:0 0 8px 8px;background:var(--card);color:var(--ink);resize:vertical}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;align-items:center}
.btn{font:inherit;font-size:13px;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;text-decoration:none}
.btn.pri{background:var(--accent);border-color:var(--accent);color:#fff}.btn[aria-disabled=true]{opacity:.4;pointer-events:none}
select.st{font:inherit;font-size:13px;padding:5px 8px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.note{font-size:12px;color:var(--mute)}.fu{background:var(--accent);color:#fff}.shot{width:84px;border:1px solid var(--line);border-radius:8px;display:block}.tip{background:var(--chip);border-radius:10px;padding:10px 14px;font-size:13px;margin-bottom:14px}.empty{text-align:center;color:var(--mute);padding:40px}
</style></head><body>
<header><div class="wrap">
<h1>Lead review queue</h1>
<div class="sub">Generated __GENERATED__. Nothing is sent automatically: edit each draft, send it yourself, then mark its status.</div>
<div class="bar">
<input id="q" placeholder="Search name, city, issue…">
<select id="tier"><option value="">All tiers</option><option>hot</option><option>warm</option><option>cold</option></select>
<select id="stf"><option value="">All statuses</option><option>new</option><option>reviewed</option><option>sent</option><option>followed_up</option><option>skip</option></select>
<button class="btn" id="exp" title="Download statuses, then run: python -m leadagent import-status statuses.json">Export statuses</button>
</div><div class="sub" id="count"></div></div></header>
<main class="wrap" id="list"></main>
<script>
const LEADS = __DATA__;
const KEY = "leadagent-status";
let saved = {}; try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const persist = () => { try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {} };
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const offerName = {wordpress:"WordPress site",custom:"Custom-coded site",chatbot:"Chatbot"};
const kindName = {new_site:"No website",rebuild:"Broken site",redesign:"Redesign",chatbot_only:"Chatbot add-on"};
function card(l){
  const st = saved[l.id]?.status || l.status;
  const draft = saved[l.id]?.draft || {};
  const offer = [l.offer.primary,l.offer.secondary].filter(Boolean).map(o=>offerName[o]).join(" + ");
  const site = l.website ? `<a href="${esc(l.website)}" target="_blank" rel="noopener">${esc(l.website.replace(/^https?:\/\//,""))}</a>` : "no website";
  const rating = l.rating ? ` · ${l.rating}★ (${l.reviews||0})` : "";
  const links = [l.maps&&`<a href="${esc(l.maps)}" target="_blank" rel="noopener">map</a>`, l.facebook&&`<a href="${esc(l.facebook)}" target="_blank" rel="noopener">facebook</a>`,
    `<a href="${esc(l.google)}" target="_blank" rel="noopener" title="Find their phone/email/Facebook on Google">google them</a>`].filter(Boolean).join(" · ");
  return `<article class="card" data-id="${l.id}">
  <div class="top"><div><div class="name">${esc(l.name)}</div>
  <div class="meta">${esc(l.category)} · ${esc(l.city)}${rating} · ${site} · ${links}</div>
  <div class="meta">${l.phone?esc(l.phone):"no phone"}${l.wa?" (mobile)":""}${l.email?" · "+esc(l.email):""}${l.platform?" · built with "+esc(l.platform):""}${l.load?` · loaded in ${l.load}s`:""}${l.psi!=null?` · PageSpeed ${l.psi}/100`:""}${!l.phone&&!l.email?' · <b>no contact yet: use "google them"</b>':""}</div></div>
  <div style="display:flex;flex-direction:column;align-items:flex-end;gap:8px"><span class="score ${l.followup?"fu":l.tier}">${l.followup?"follow-up due":l.score+" · "+l.tier}</span>
  ${l.shot?`<a href="${esc(l.shot)}" target="_blank" title="Their site on a phone today: attach this to your WhatsApp"><img class="shot" src="${esc(l.shot)}" alt="phone screenshot"></a>`:""}</div></div>
  <ul>${l.findings.slice(0,5).map(f=>`<li>${esc(f.t.charAt(0).toUpperCase()+f.t.slice(1))}</li>`).join("")}</ul>
  <div class="chips"><span class="chip">${esc(kindName[l.offer.kind]||l.offer.kind)}</span><span class="chip">Pitch: ${esc(offer)}</span><span class="chip">${esc(l.engine)}</span></div>
  <div class="tabs"><button class="on" data-t="email">Email</button><button data-t="wa">WhatsApp</button></div>
  <div class="pane" data-p="email"><input class="subj" value="${esc(draft.subject ?? l.subject)}"><textarea class="eb">${esc(draft.email ?? l.emailBody)}</textarea></div>
  <div class="pane" data-p="wa" hidden><textarea class="wb" style="min-height:140px;border-radius:8px">${esc(draft.wa ?? l.waMsg)}</textarea></div>
  <div class="actions">
   <button class="btn" data-a="copy">Copy</button>
   <button class="btn" data-a="ai" title="Paste into a free AI chat (e.g. claude.ai) to polish it, or translate to Sinhala/Tamil">Copy AI prompt</button>
   <a class="btn pri" data-a="mail" ${l.email?"":'aria-disabled="true"'} target="_blank">Open in email</a>
   <a class="btn pri" data-a="wa" ${l.wa?"":'aria-disabled="true" title="No mobile number found"'} target="_blank" rel="noopener">Open in WhatsApp</a>
   <select class="st">${["new","reviewed","sent","followed_up","replied","won","lost","skip"].map(s=>`<option ${s===st?"selected":""}>${s}</option>`).join("")}</select>
   <span class="note">${esc(l.id)}</span>
  </div></article>`;
}
function render(){
  const q=document.getElementById("q").value.toLowerCase(), t=document.getElementById("tier").value, sf=document.getElementById("stf").value;
  const list=LEADS.filter(l=>{const st=saved[l.id]?.status||l.status;
    return (!t||l.tier===t)&&(!sf||st===sf)&&(!q||(l.name+" "+l.city+" "+l.category+" "+l.findings.map(f=>f.t).join(" ")).toLowerCase().includes(q));});
  document.getElementById("list").innerHTML = list.map(card).join("") || '<div class="empty">No leads match.</div>';
  const fu=LEADS.filter(l=>l.followup).length;
  document.getElementById("count").textContent = `${list.length} of ${LEADS.length} leads` + (fu?` · ${fu} follow-up${fu>1?"s":""} due`:"");
  document.querySelectorAll(".card").forEach(wire);
}
function wire(el){
  const l=LEADS.find(x=>x.id===el.dataset.id);
  const subj=el.querySelector(".subj"), eb=el.querySelector(".eb"), wb=el.querySelector(".wb");
  const mail=el.querySelector('[data-a=mail]'), wa=el.querySelector('[data-a=wa]');
  const upd=()=>{ if(l.email) mail.href=`mailto:${l.email}?subject=${encodeURIComponent(subj.value)}&body=${encodeURIComponent(eb.value)}`;
    if(l.wa) wa.href=`https://wa.me/${l.wa}?text=${encodeURIComponent(wb.value)}`; };
  const keep=()=>{ saved[l.id]={...(saved[l.id]||{}),draft:{subject:subj.value,email:eb.value,wa:wb.value}}; persist(); upd(); };
  [subj,eb,wb].forEach(x=>x.addEventListener("input",keep)); upd();
  el.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>{el.querySelectorAll(".tabs button").forEach(x=>x.classList.toggle("on",x===b));
    el.querySelectorAll(".pane").forEach(p=>p.hidden=p.dataset.p!==b.dataset.t);});
  el.querySelector('[data-a=copy]').onclick=e=>{const emailOn=!el.querySelector('[data-p=email]').hidden;
    navigator.clipboard.writeText(emailOn?`Subject: ${subj.value}\n\n${eb.value}`:wb.value).then(()=>{e.target.textContent="Copied";setTimeout(()=>e.target.textContent="Copy",1200);});};
  el.querySelector('[data-a=ai]').onclick=e=>navigator.clipboard.writeText(l.aiPrompt).then(()=>{e.target.textContent="Prompt copied";setTimeout(()=>e.target.textContent="Copy AI prompt",1500);});
  el.querySelector(".st").onchange=e=>{saved[l.id]={...(saved[l.id]||{}),status:e.target.value,at:new Date().toISOString()};persist();};
}
document.getElementById("exp").onclick=()=>{const out={};for(const[id,v]of Object.entries(saved))if(v.status)out[id]={status:v.status,at:v.at};
  const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)],{type:"application/json"}));a.download="statuses.json";a.click();};
["q","tier","stf"].forEach(id=>document.getElementById(id).addEventListener("input",render));
render();
</script></body></html>
"""

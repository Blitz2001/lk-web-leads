"""Small helpers: phone normalisation, URL cleanup, slugs."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

# Sri Lankan mobile numbers start with 07x (70-78). Landlines (011, 081, 091...)
# usually aren't on WhatsApp.
_MOBILE_RE = re.compile(r"^947[0-8]\d{7}$")


def normalize_lk_phone(raw: str | None) -> str | None:
    """Return a Sri Lankan number as digits in international form (94XXXXXXXXX).

    Accepts '077 123 4567', '+94 77 1234567', '0094771234567', '(011) 2345678'.
    If several numbers are given ('077..., 011...'), the first mobile wins.
    """
    if not raw:
        return None
    candidates = re.split(r"[;,/]| or ", raw)
    normalized = []
    for c in candidates:
        d = re.sub(r"\D", "", c)
        if d.startswith("0094"):
            d = d[2:]
        elif d.startswith("0") and len(d) == 10:
            d = "94" + d[1:]
        elif len(d) == 9 and d[0] != "0":
            d = "94" + d
        if d.startswith("94") and len(d) == 11:
            normalized.append(d)
    if not normalized:
        return None
    for n in normalized:
        if _MOBILE_RE.match(n):
            return n
    return normalized[0]


def is_mobile(phone94: str | None) -> bool:
    return bool(phone94 and _MOBILE_RE.match(phone94))


def pretty_phone(phone94: str | None) -> str:
    if not phone94:
        return ""
    return f"+94 {phone94[2:4]} {phone94[4:7]} {phone94[7:]}"


def clean_url(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip().split()[0] if raw.strip() else ""
    if not raw:
        return None
    if not re.match(r"^https?://", raw, re.I):
        raw = "http://" + raw
    return raw


def domain_of(url: str | None) -> str:
    if not url:
        return ""
    host = urlparse(url).hostname or ""
    return host.lower().removeprefix("www.")


def lead_id(name: str, city: str, phone: str | None = None) -> str:
    key = f"{name.strip().lower()}|{city.strip().lower()}|{phone or ''}"
    return hashlib.sha1(key.encode()).hexdigest()[:10]

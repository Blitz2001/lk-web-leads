"""Where leads come from.

* OpenStreetMap (Overpass API): free, no key. Coverage in Sri Lanka is patchy
  but includes plenty of hotels, guest houses, restaurants and clinics.
* Google Places API (New): much better coverage, needs GOOGLE_MAPS_API_KEY.
  Text Search returns up to 60 results per query (3 pages of 20).
* CSV import: your own list (from Google Maps, Facebook, directories, referrals).
"""
from __future__ import annotations

import csv
import json
import os
import time

import requests

from .util import clean_url, lead_id, normalize_lk_phone

UA = "LeadAgent/1.0 (small-business website audit)"

CITIES: dict[str, tuple[float, float]] = {
    "colombo": (6.9271, 79.8612), "dehiwala": (6.8511, 79.8653),
    "mount lavinia": (6.8390, 79.8630), "nugegoda": (6.8649, 79.8997),
    "maharagama": (6.8480, 79.9265), "moratuwa": (6.7730, 79.8816),
    "battaramulla": (6.8990, 79.9180), "kotte": (6.8868, 79.9187),
    "gampaha": (7.0917, 79.9999), "negombo": (7.2083, 79.8358),
    "kalutara": (6.5854, 79.9607), "panadura": (6.7132, 79.9026),
    "kandy": (7.2906, 80.6337), "nuwara eliya": (6.9497, 80.7891),
    "galle": (6.0535, 80.2210), "unawatuna": (6.0100, 80.2490),
    "hikkaduwa": (6.1395, 80.1063), "bentota": (6.4210, 80.0000),
    "matara": (5.9549, 80.5550), "mirissa": (5.9483, 80.4716),
    "weligama": (5.9750, 80.4297), "tangalle": (6.0240, 80.7940),
    "ella": (6.8667, 81.0466), "badulla": (6.9934, 81.0550),
    "kurunegala": (7.4863, 80.3647), "anuradhapura": (8.3114, 80.4037),
    "polonnaruwa": (7.9403, 81.0188), "dambulla": (7.8742, 80.6511),
    "sigiriya": (7.9570, 80.7603), "trincomalee": (8.5874, 81.2152),
    "batticaloa": (7.7310, 81.6747), "arugam bay": (6.8400, 81.8360),
    "jaffna": (9.6615, 80.0255), "ratnapura": (6.6828, 80.3992),
    "chilaw": (7.5758, 79.7953), "kegalle": (7.2513, 80.3464),
}

# category -> (Overpass tag filters, Google search phrase)
CATEGORIES: dict[str, tuple[list[str], str]] = {
    "hotels": (['["tourism"~"^(hotel|guest_house|hostel|motel|apartment|chalet)$"]'], "hotels and guest houses"),
    "restaurants": (['["amenity"~"^(restaurant|cafe|fast_food)$"]'], "restaurants and cafes"),
    "clinics": (['["amenity"~"^(clinic|doctors|dentist)$"]', '["healthcare"~"^(clinic|dentist|doctor|physiotherapist)$"]'], "medical and dental clinics"),
    "salons": (['["shop"~"^(hairdresser|beauty|cosmetics)$"]', '["amenity"="spa"]', '["leisure"="spa"]'], "beauty salons and spas"),
    "tours": (['["shop"="travel_agency"]', '["office"~"^(travel_agent|guide)$"]', '["tourism"="information"]["information"="office"]'], "tour operators and travel agents"),
    "gyms": (['["leisure"~"^(fitness_centre|sports_centre)$"]'], "gyms and fitness centres"),
    "education": (['["amenity"~"^(language_school|driving_school|music_school|college|prep_school)$"]', '["office"="educational_institution"]'], "tuition classes and private institutes"),
    "retail": (['["shop"~"^(clothes|shoes|jewelry|furniture|electronics|mobile_phone|hardware|bakery|optician|gift)$"]'], "shops"),
    "auto": (['["shop"~"^(car|car_repair|car_parts|motorcycle|tyres)$"]', '["amenity"="car_wash"]'], "vehicle sales and repair"),
    "realestate": (['["office"="estate_agent"]', '["office"="construction_company"]', '["craft"="builder"]'], "real estate and construction companies"),
    "professional": (['["office"~"^(lawyer|accountant|insurance|architect|notary|consulting)$"]'], "lawyers, accountants and consultants"),
}


CITY_CACHE = os.path.join(os.path.expanduser("~"), ".leadagent_cities.json")


def _load_city_cache() -> dict:
    try:
        with open(CITY_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def geocode_city(city: str) -> tuple[float, float] | None:
    """Look up any Sri Lankan town on OpenStreetMap Nominatim (free, 1 request/sec). Cached."""
    key = city.strip().lower()
    cache = _load_city_cache()
    if key in cache:
        return tuple(cache[key])
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "countrycodes": "lk", "format": "json", "limit": 1},
            headers={"User-Agent": UA}, timeout=20,
        )
        r.raise_for_status()
        hits = r.json()
    except (requests.RequestException, ValueError):
        return None
    if not hits:
        return None
    coords = (float(hits[0]["lat"]), float(hits[0]["lon"]))
    cache[key] = coords
    try:
        with open(CITY_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except OSError:
        pass
    time.sleep(1)
    return coords


def resolve_city(city: str) -> tuple[float, float]:
    key = city.strip().lower()
    if key in CITIES:
        return CITIES[key]
    coords = geocode_city(city)
    if coords:
        return coords
    raise SystemExit(
        f"Couldn't find '{city}' in Sri Lanka. Check the spelling (e.g. 'Nuwara Eliya'), "
        f"pick a nearby town, or use one of: {', '.join(sorted(CITIES))}."
    )


# ---------------------------------------------------------------- OpenStreetMap
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def overpass_query(lat: float, lon: float, radius_m: int, filters: list[str]) -> str:
    parts = "\n".join(
        f'  nwr["name"]{f}(around:{radius_m},{lat},{lon});' for f in filters
    )
    return f"[out:json][timeout:90];\n(\n{parts}\n);\nout center tags;"


def parse_overpass(data: dict, city: str, category: str) -> list[dict]:
    leads = []
    for el in data.get("elements", []):
        t = el.get("tags", {})
        name = t.get("name:en") or t.get("name")
        if not name:
            continue
        phone = normalize_lk_phone(
            t.get("contact:mobile") or t.get("phone") or t.get("contact:phone") or t.get("mobile")
        )
        website = clean_url(t.get("website") or t.get("contact:website") or t.get("url"))
        facebook = t.get("contact:facebook") or t.get("facebook")
        addr = ", ".join(
            x for x in [t.get("addr:housenumber"), t.get("addr:street"), t.get("addr:city")] if x
        )
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        leads.append({
            "id": lead_id(name, city, phone),
            "name": name,
            "category": category,
            "city": city.title(),
            "address": addr,
            "phone": phone,
            "email": t.get("email") or t.get("contact:email"),
            "website": website,
            "facebook": clean_url(facebook) if facebook and "." in facebook else None,
            "maps_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            "rating": None,
            "reviews": None,
            "lat": lat,
            "lon": lon,
            "source": "osm",
        })
    return leads


def from_osm(city: str, category: str, radius_km: float = 5, limit: int = 50) -> list[dict]:
    lat, lon = resolve_city(city)
    filters, _ = CATEGORIES[category]
    q = overpass_query(lat, lon, int(radius_km * 1000), filters)
    last_err = None
    for attempt in range(2):
        for url in OVERPASS_URLS:
            try:
                r = requests.post(url, data={"data": q}, headers={"User-Agent": UA}, timeout=120)
                if r.status_code in (429, 504):  # busy: free public server, wait and retry
                    last_err = f"server busy ({r.status_code})"
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                leads = _dedupe(parse_overpass(r.json(), city, category))
                # leads with a phone or website first: they're contactable
                leads.sort(key=lambda l: (not l["phone"] and not l["email"], l["website"] is not None))
                return leads[:limit]
            except (requests.RequestException, ValueError) as e:
                last_err = e
                time.sleep(2)
    raise RuntimeError(
        f"OpenStreetMap search failed ({last_err}). The free server may be busy: wait a minute and try again."
    )


# ---------------------------------------------------------------- Google Places
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELDS = ",".join([
    "places.id", "places.displayName", "places.formattedAddress",
    "places.nationalPhoneNumber", "places.internationalPhoneNumber",
    "places.websiteUri", "places.rating", "places.userRatingCount",
    "places.googleMapsUri", "places.businessStatus", "places.location",
    "nextPageToken",
])


def parse_places(data: dict, city: str, category: str) -> list[dict]:
    leads = []
    for p in data.get("places", []):
        if p.get("businessStatus") not in (None, "OPERATIONAL"):
            continue
        name = (p.get("displayName") or {}).get("text")
        if not name:
            continue
        phone = normalize_lk_phone(p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber"))
        loc = p.get("location") or {}
        leads.append({
            "id": lead_id(name, city, phone),
            "name": name,
            "category": category,
            "city": city.title(),
            "address": p.get("formattedAddress", ""),
            "phone": phone,
            "email": None,
            "website": clean_url(p.get("websiteUri")),
            "facebook": None,
            "maps_url": p.get("googleMapsUri"),
            "rating": p.get("rating"),
            "reviews": p.get("userRatingCount"),
            "lat": loc.get("latitude"),
            "lon": loc.get("longitude"),
            "source": "google",
        })
    return leads


def from_google(city: str, category: str, limit: int = 60, query: str | None = None) -> list[dict]:
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        raise SystemExit("Set GOOGLE_MAPS_API_KEY to use --source google (Places API (New) must be enabled).")
    phrase = query or CATEGORIES.get(category, ([], category))[1]
    body: dict = {"textQuery": f"{phrase} in {city}, Sri Lanka", "pageSize": 20, "regionCode": "LK"}
    if city.lower() in CITIES:
        lat, lon = CITIES[city.lower()]
        body["locationBias"] = {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": 15000.0}}
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": PLACES_FIELDS, "Content-Type": "application/json"}
    leads: list[dict] = []
    while len(leads) < limit:
        r = requests.post(PLACES_URL, json=body, headers=headers, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Places API {r.status_code}: {r.text[:300]}")
        data = r.json()
        leads += parse_places(data, city, category)
        token = data.get("nextPageToken")
        if not token:
            break
        body["pageToken"] = token
        time.sleep(2)  # token needs a moment to become valid
    return _dedupe(leads)[:limit]


# ---------------------------------------------------------------- CSV
def from_csv(path: str, default_city: str = "", default_category: str = "other") -> list[dict]:
    """Columns (case-insensitive, all optional except name):
    name, category, city, address, phone, email, website, facebook, maps_url, rating, reviews
    """
    leads = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            name = row.get("name")
            if not name:
                continue
            city = row.get("city") or default_city
            phone = normalize_lk_phone(row.get("phone"))
            leads.append({
                "id": lead_id(name, city, phone),
                "name": name,
                "category": row.get("category") or default_category,
                "city": city.title(),
                "address": row.get("address", ""),
                "phone": phone,
                "email": row.get("email") or None,
                "website": clean_url(row.get("website")),
                "facebook": clean_url(row.get("facebook")),
                "maps_url": row.get("maps_url") or None,
                "rating": float(row["rating"]) if row.get("rating") else None,
                "reviews": int(float(row["reviews"])) if row.get("reviews") else None,
                "lat": None,
                "lon": None,
                "source": "csv",
            })
    return _dedupe(leads)


def _dedupe(leads: list[dict]) -> list[dict]:
    seen, out = set(), []
    for l in leads:
        if l["id"] in seen:
            continue
        seen.add(l["id"])
        out.append(l)
    return out

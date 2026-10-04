#!/usr/bin/env python3
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

OUT = "signals.json"
QUERY = '(war OR invasion OR ceasefire OR peace OR nuclear OR missile OR "terror attack" OR terrorism OR pandemic OR outbreak OR bioweapon OR "biological weapon" OR genocide OR earthquake OR tsunami OR wildfire OR flood OR "artificial intelligence" OR AI)'
URL = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode({
    "query": QUERY,
    "mode": "ArtList",
    "format": "json",
    "sort": "datedesc",
    "maxrecords": 250,
})

CATEGORIES = [
    ("CEASEFIRE", 1, ["ceasefire", "truce", "peace deal", "peace agreement", "war ends", "war ended", "hostilities end"]),
    ("NUCLEAR", 3, ["nuclear", "atomic", "warhead", "uranium", "plutonium", "icbm", "ballistic missile", "nuclear-capable"]),
    ("GENOCIDE", 3, ["genocide", "mass atrocity", "ethnic cleansing", "massacre"]),
    ("TERROR", 3, ["terror attack", "terrorist attack", "terrorism", "suicide bombing", "bomb attack"]),
    ("BIO", 2, ["bioweapon", "biological weapon", "biosecurity", "gain of function", "pathogen research"]),
    ("PANDEMIC", 2, ["pandemic", "outbreak", "epidemic", "zoonotic", "virus strain", "variant of concern"]),
    ("AI", 2, ["artificial intelligence", " ai ", "ai model", "ai system", "autonomous weapon", "ai weapon"]),
    ("DISASTER", 2, ["earthquake", "tsunami", "wildfire", "hurricane", "cyclone", "flood", "dam collapse", "industrial disaster", "chemical leak"]),
    ("WAR", 3, ["invasion", "war begins", "war started", "declares war", "major offensive", "airstrike", "missile strike", "troops enter"]),
    ("CONFLICT", 2, ["war", "conflict", "clashes", "fighting", "shelling", "drone strike", "military operation"]),
]

HIGH_IMPACT = ["killed", "dead", "casualties", "evacuation", "state of emergency", "massive", "major", "large-scale", "nuclear", "genocide", "pandemic"]

def clean_title(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def classify(title):
    t = " " + title.lower() + " "
    for cat, sev, terms in CATEGORIES:
        if any(term in t for term in terms):
            impact = 1 if any(x in t for x in HIGH_IMPACT) else 0
            return cat, min(3, sev + impact)
    return "CONFLICT", 1

def parse_seen(raw):
    raw = str(raw or "")
    try:
        if re.fullmatch(r"\d{14}", raw):
            return datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass
    return None

def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "DoomsdayClock/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)

    items, seen_titles = [], set()
    for a in payload.get("articles", []):
        title = clean_title(a.get("title"))
        url = a.get("url")
        if not title or not url:
            continue
        key = re.sub(r"[^a-z0-9]+", " ", title.lower())[:140]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        category, severity = classify(title)
        items.append({
            "title": title,
            "url": url,
            "category": category,
            "severity": severity,
            "seen": parse_seen(a.get("seendate")),
            "domain": a.get("domain") or "",
            "language": a.get("language") or "",
            "sourcecountry": a.get("sourcecountry") or "",
        })
        if len(items) >= 30:
            break

    data = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "GDELT 2.1 DOC API",
        "query": QUERY,
        "items": items,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

if __name__ == "__main__":
    main()

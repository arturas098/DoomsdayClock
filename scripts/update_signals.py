#!/usr/bin/env python3
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

OUT = "signals.json"
QUERY = '(war OR invasion OR ceasefire OR nuclear OR missile OR "terror attack" OR pandemic OR outbreak OR bioweapon OR genocide OR earthquake OR tsunami OR wildfire OR flood OR "artificial intelligence") when:1d'
RSS_URL = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
    "q": QUERY,
    "hl": "en-US",
    "gl": "US",
    "ceid": "US:en",
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

def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def classify(title):
    t = " " + title.lower() + " "
    for cat, sev, terms in CATEGORIES:
        if any(term in t for term in terms):
            impact = 1 if any(x in t for x in HIGH_IMPACT) else 0
            return cat, min(3, sev + impact)
    return "CONFLICT", 1

def parse_pubdate(raw):
    try:
        d = parsedate_to_datetime(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        return None

def main():
    req = urllib.request.Request(RSS_URL, headers={
        "User-Agent": "Mozilla/5.0 DoomsdayClock/1.0",
        "Accept": "application/rss+xml, application/xml, text/xml",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        xml_data = r.read()

    root = ET.fromstring(xml_data)
    items = []
    seen_titles = set()

    for node in root.findall("./channel/item"):
        title = clean(node.findtext("title"))
        url = clean(node.findtext("link"))
        pub = clean(node.findtext("pubDate"))
        source_node = node.find("source")
        source = clean(source_node.text if source_node is not None else "")
        if not title or not url:
            continue

        key = re.sub(r"[^a-z0-9]+", " ", title.lower())[:160]
        if key in seen_titles:
            continue
        seen_titles.add(key)

        category, severity = classify(title)
        items.append({
            "title": title,
            "url": url,
            "category": category,
            "severity": severity,
            "seen": parse_pubdate(pub),
            "domain": source,
            "language": "English",
            "sourcecountry": "",
        })
        if len(items) >= 30:
            break

    data = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Google News RSS",
        "query": QUERY,
        "items": items,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

if __name__ == "__main__":
    main()

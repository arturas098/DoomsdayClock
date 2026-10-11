#!/usr/bin/env python3
import json
import os
import re
import time
import urllib.error
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


def fetch_rss(max_attempts=4):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DoomsdayClock/1.0; +https://github.com/arturas098/DoomsdayClock)",
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
        "Cache-Control": "no-cache",
    }

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(RSS_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            code = getattr(exc, "code", None)
            print(f"RSS fetch attempt {attempt}/{max_attempts} failed: {exc}")

            # 4xx other than rate limiting is unlikely to recover immediately.
            if code is not None and 400 <= code < 500 and code != 429:
                break

            if attempt < max_attempts:
                time.sleep(3 * attempt)

    raise last_error or RuntimeError("RSS fetch failed")


def keep_previous_feed(error):
    if not os.path.exists(OUT):
        return False

    try:
        with open(OUT, "r", encoding="utf-8") as f:
            previous = json.load(f)
        count = len(previous.get("items", [])) if isinstance(previous, dict) else 0
        print(f"WARNING: live source unavailable ({error}). Keeping existing {OUT} with {count} items.")
        return True
    except Exception as exc:
        print(f"Existing {OUT} could not be reused: {exc}")
        return False


def main():
    try:
        xml_data = fetch_rss()
        root = ET.fromstring(xml_data)
    except Exception as exc:
        # A temporary Google News 503/429 should not mark the scheduled workflow as failed.
        # The website can safely keep serving the last successfully generated feed.
        if keep_previous_feed(exc):
            return
        raise

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

    print(f"Updated {OUT} with {len(items)} items.")


if __name__ == "__main__":
    main()

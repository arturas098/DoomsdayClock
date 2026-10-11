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
from html.parser import HTMLParser
from urllib.parse import urljoin

OUT = "signals.json"
QUERY = '(war OR invasion OR ceasefire OR nuclear OR missile OR "terror attack" OR pandemic OR outbreak OR bioweapon OR genocide OR earthquake OR tsunami OR wildfire OR flood OR "artificial intelligence") when:1d'
GOOGLE_RSS_URL = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
    "q": QUERY,
    "hl": "en-US",
    "gl": "US",
    "ceid": "US:en",
})
LRT_ENGLISH_URL = "https://www.lrt.lt/en/news-in-english"

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

# Extra regional/security terms so LRT English can contribute useful Baltic/NATO items
# even when the headline does not literally say "war".
RELEVANCE_TERMS = [
    "war", "invasion", "ceasefire", "truce", "peace deal", "conflict", "clashes",
    "airstrike", "missile", "drone strike", "shelling", "military", "troops",
    "nuclear", "atomic", "warhead", "uranium", "plutonium", "icbm",
    "terror", "bombing", "genocide", "massacre", "ethnic cleansing",
    "pandemic", "outbreak", "epidemic", "virus", "biosecurity", "bioweapon",
    "earthquake", "tsunami", "wildfire", "hurricane", "cyclone", "flood",
    "industrial disaster", "chemical leak", "artificial intelligence", " ai ",
    "autonomous weapon", "nato", "ukraine", "russia", "belarus", "defence", "defense"
]


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def classify(title):
    t = " " + title.lower() + " "
    for cat, sev, terms in CATEGORIES:
        if any(term in t for term in terms):
            impact = 1 if any(x in t for x in HIGH_IMPACT) else 0
            return cat, min(3, sev + impact)

    # LRT often uses regional-security wording without an explicit "war" keyword.
    if any(x in t for x in ["nato", "ukraine", "russia", "belarus", "defence", "defense", "military"]):
        return "CONFLICT", 2
    return "CONFLICT", 1


def relevant(title):
    t = " " + title.lower() + " "
    return any(term in t for term in RELEVANCE_TERMS)


def parse_pubdate(raw):
    try:
        d = parsedate_to_datetime(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def fetch_url(url, max_attempts=4, accept="*/*"):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DoomsdayClock/1.1; +https://github.com/arturas098/DoomsdayClock)",
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.8",
        "Cache-Control": "no-cache",
    }

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            code = getattr(exc, "code", None)
            print(f"Fetch attempt {attempt}/{max_attempts} failed for {url}: {exc}")

            if code is not None and 400 <= code < 500 and code != 429:
                break
            if attempt < max_attempts:
                time.sleep(3 * attempt)

    raise last_error or RuntimeError(f"Fetch failed: {url}")


def google_items():
    xml_data = fetch_url(
        GOOGLE_RSS_URL,
        accept="application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    )
    root = ET.fromstring(xml_data)
    items = []

    for node in root.findall("./channel/item"):
        title = clean(node.findtext("title"))
        url = clean(node.findtext("link"))
        pub = clean(node.findtext("pubDate"))
        source_node = node.find("source")
        source = clean(source_node.text if source_node is not None else "")
        if not title or not url:
            continue

        category, severity = classify(title)
        items.append({
            "title": title,
            "url": url,
            "category": category,
            "severity": severity,
            "seen": parse_pubdate(pub),
            "domain": source or "Google News",
            "language": "English",
            "sourcecountry": "",
        })
        if len(items) >= 35:
            break
    return items


class LRTEnglishParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current_href = None
        self.current_text = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href", "")
        if "/en/news-in-english/" in href:
            self.current_href = urljoin(LRT_ENGLISH_URL, href)
            self.current_text = []

    def handle_data(self, data):
        if self.current_href:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current_href:
            title = clean(" ".join(self.current_text))
            if title:
                self.links.append((title, self.current_href))
            self.current_href = None
            self.current_text = []


def lrt_items():
    html_data = fetch_url(
        LRT_ENGLISH_URL,
        max_attempts=3,
        accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    ).decode("utf-8", errors="ignore")

    parser = LRTEnglishParser()
    parser.feed(html_data)

    items = []
    seen_urls = set()
    for title, url in parser.links:
        if url in seen_urls or not relevant(title):
            continue
        seen_urls.add(url)
        category, severity = classify(title)
        items.append({
            "title": title,
            "url": url,
            "category": category,
            "severity": severity,
            # Listing-page HTML does not expose a stable machine-readable timestamp
            # next to every link, so leave this null instead of inventing one.
            "seen": None,
            "domain": "LRT English",
            "language": "English",
            "sourcecountry": "LT",
        })
        if len(items) >= 12:
            break
    return items


def load_previous_items():
    if not os.path.exists(OUT):
        return []
    try:
        with open(OUT, "r", encoding="utf-8") as f:
            previous = json.load(f)
        return previous.get("items", []) if isinstance(previous, dict) else []
    except Exception as exc:
        print(f"Could not load previous feed: {exc}")
        return []


def dedupe(items, limit=40):
    out = []
    seen_titles = set()
    seen_urls = set()
    for item in items:
        title = clean(item.get("title"))
        url = clean(item.get("url"))
        if not title or not url:
            continue
        key = re.sub(r"[^a-z0-9]+", " ", title.lower())[:160]
        if key in seen_titles or url in seen_urls:
            continue
        seen_titles.add(key)
        seen_urls.add(url)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def main():
    previous_items = load_previous_items()
    google = []
    lrt = []
    errors = []

    try:
        google = google_items()
        print(f"Google News: {len(google)} items")
    except Exception as exc:
        errors.append(f"Google News: {exc}")
        print(f"WARNING: Google News unavailable: {exc}")

    try:
        lrt = lrt_items()
        print(f"LRT English: {len(lrt)} relevant items")
    except Exception as exc:
        errors.append(f"LRT English: {exc}")
        print(f"WARNING: LRT English unavailable: {exc}")

    # Put a few LRT English regional items near the top, then global Google results,
    # then the remaining LRT items. If both sources are temporarily unavailable,
    # keep the last good feed so the website and workflow stay healthy.
    merged = dedupe(lrt[:6] + google + lrt[6:], limit=40)
    if not merged:
        if previous_items:
            print(f"WARNING: all live sources unavailable/empty. Keeping existing {OUT} with {len(previous_items)} items.")
            return
        raise RuntimeError("No crisis feed items available from Google News or LRT English")

    data = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Google News RSS + LRT English",
        "query": QUERY,
        "source_status": {
            "google_news_items": len(google),
            "lrt_english_items": len(lrt),
            "errors": errors,
        },
        "items": merged,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Updated {OUT} with {len(merged)} merged items ({len(lrt)} LRT, {len(google)} Google candidates).")


if __name__ == "__main__":
    main()

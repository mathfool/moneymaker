"""Free news sources per symbol: Yahoo Finance (via yfinance), Google News RSS, SEC EDGAR 8-K filings.
Merged, de-duplicated, keyword-tagged, cached in SQLite for 30 minutes."""
from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime

import pandas as pd
import requests
import yfinance as yf

from . import db

HEADERS = {"User-Agent": "moneymaker/0.1 (personal research tool; contact: danielqinling@gmail.com)"}
CACHE_MINUTES = 30
ATOM = "{http://www.w3.org/2005/Atom}"

# keyword -> tag. Order matters: first match wins for the primary tag, all matches are kept.
TAGS: list[tuple[str, re.Pattern]] = [
    ("财报", re.compile(r"\b(earnings|eps|revenue|quarter|q[1-4]\b|guidance|beat|miss(es|ed)?|results|outlook|forecast)\b", re.I)),
    ("评级", re.compile(r"\b(upgrade[sd]?|downgrade[sd]?|price target|rating|initiat(es|ed)|overweight|underweight|outperform|buy rating|sell rating)\b", re.I)),
    ("并购", re.compile(r"\b(acqui(re|res|red|sition)|merger|merge|buyout|takeover|to buy|deal to)\b", re.I)),
    ("合同/产品", re.compile(r"\b(contract|partnership|partners? with|launch(es|ed)?|unveil|approv(al|ed|es)|fda|order[s]? from|wins?\b|award(ed)?)\b", re.I)),
    ("监管/诉讼", re.compile(r"\b(sec\b|lawsuit|investigat(ion|es)|probe|antitrust|tariff|regulat|subpoena|fine[ds]?\b|recall)\b", re.I)),
    ("高管/内部", re.compile(r"\b(ceo|cfo|resign|steps down|appoint|insider|buyback|repurchase|dividend|split)\b", re.I)),
]


def _tag(title: str) -> list[str]:
    return [t for t, rx in TAGS if rx.search(title)]


def _iso(dt) -> str | None:
    try:
        ts = pd.Timestamp(dt)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:  # noqa: BLE001
        return None


def _yahoo(symbol: str) -> list[dict]:
    out = []
    try:
        for n in yf.Ticker(symbol).news or []:
            c = n.get("content", n)
            title = c.get("title")
            if not title:
                continue
            url = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or n.get("link")
            src = (c.get("provider") or {}).get("displayName") or n.get("publisher") or "Yahoo Finance"
            when = c.get("pubDate") or n.get("providerPublishTime")
            if isinstance(when, (int, float)):
                when = pd.Timestamp(when, unit="s", tz="UTC")
            out.append({"title": title.strip(), "url": url, "source": src, "time": _iso(when), "kind": "news", "via": "Yahoo"})
    except Exception as e:  # noqa: BLE001
        print("yahoo news error", symbol, e)
    return out


def _google(symbol: str, name: str | None) -> list[dict]:
    out = []
    q = f'"{symbol}" stock' if not name else f'"{symbol}" OR "{name}" stock'
    url = "https://news.google.com/rss/search?q=" + requests.utils.quote(q) + "&hl=en-US&gl=US&ceid=US:en"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        for it in ET.fromstring(r.content).findall(".//item")[:40]:
            title = html.unescape(it.findtext("title") or "")
            src = it.findtext("source") or ""
            if " - " in title:                      # Google appends " - Publisher" to every title
                title, tail = title.rsplit(" - ", 1)
                src = src or tail
            when = it.findtext("pubDate")
            out.append({"title": title.strip(), "url": it.findtext("link"), "source": src.strip() or "Google News",
                        "time": _iso(parsedate_to_datetime(when)) if when else None, "kind": "news", "via": "Google"})
    except Exception as e:  # noqa: BLE001
        print("google news error", symbol, e)
    return out


def _sec(symbol: str) -> list[dict]:
    out = []
    url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=" + symbol
           + "&type=8-K&dateb=&owner=include&count=20&output=atom")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        for e in ET.fromstring(r.content).findall(f".//{ATOM}entry"):
            title = e.findtext(f"{ATOM}title") or "8-K"
            summary = re.sub(r"<[^>]+>", " ", e.findtext(f"{ATOM}summary") or "")
            items = re.findall(r"Item\s+(\d+\.\d+)", summary)
            link = e.find(f"{ATOM}link")
            href = link.get("href") if link is not None else None
            when = e.findtext(f"{ATOM}updated")
            label = "8-K 公告"
            if "2.02" in items:
                label = "8-K 财报公告"
            elif "1.01" in items:
                label = "8-K 重大协议"
            elif "5.02" in items:
                label = "8-K 高管变动"
            elif "8.01" in items:
                label = "8-K 其他事项"
            out.append({"title": f"{label}" + (f"（Item {', '.join(sorted(set(items)))}）" if items else "") + " · " + title.split(" - ")[-1].strip(),
                        "url": href, "source": "SEC EDGAR", "time": _iso(when), "kind": "filing", "via": "SEC",
                        "items": sorted(set(items))})
    except Exception as e:  # noqa: BLE001
        print("sec error", symbol, e)
    return out


def _mentions(title: str, symbol: str, name: str | None) -> bool:
    t = title.lower()
    if re.search(r"\b" + re.escape(symbol.lower()) + r"\b", t):
        return True
    if name:
        first = name.lower().split()[0]
        if len(first) >= 3 and first in t:
            return True
    return False


def fetch(symbol: str, name: str | None = None) -> list[dict]:
    with ThreadPoolExecutor(max_workers=3) as ex:
        fy, fg, fs = ex.submit(_yahoo, symbol), ex.submit(_google, symbol, name), ex.submit(_sec, symbol)
        yahoo = [i for i in fy.result() if _mentions(i["title"], symbol, name)]   # Yahoo's feed mixes in unrelated stories
        items = yahoo + fg.result() + fs.result()
    seen: set[str] = set()
    merged = []
    for it in items:
        key = re.sub(r"[^a-z0-9]+", " ", (it["title"] or "").lower()).strip()[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        it["tags"] = (["公告"] if it["kind"] == "filing" else []) + _tag(it["title"])
        if it["kind"] == "filing" and "2.02" in (it.get("items") or []):
            it["tags"].append("财报")
        merged.append(it)
    merged.sort(key=lambda x: x.get("time") or "", reverse=True)
    return merged


def get(symbol: str, name: str | None = None, refresh: bool = True) -> list[dict]:
    symbol = symbol.upper()
    row = db.get_news(symbol)
    if row:
        age_min = (pd.Timestamp.utcnow() - pd.Timestamp(row["updated"])).total_seconds() / 60
        if age_min < CACHE_MINUTES or not refresh:
            return row["items"]
    items = fetch(symbol, name)
    if items or not row:
        db.save_news(symbol, items)
        return items
    return row["items"]

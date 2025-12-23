#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# ================= CONFIG =================
INPUT_M3U  = "live_epg_sports.m3u"
OUTPUT_M3U = "live_match.m3u"

EPG_URL = "https://raw.githubusercontent.com/karepech/Epgku/main/epg_wib_sports.xml"

LIVE_EARLY_MINUTES = 30
SOCCER_DURATION = timedelta(hours=5)
RACE_DURATION   = timedelta(hours=4)

NOW = datetime.now()  # WIB (EPG sudah WIB)

BLOCK_WORDS = [
    "replay", "highlight", "highlights",
    "goals of the season", "magazine",
    "review", "netbusters", "the final",
    "classic", "rerun"
]

RACE_WORDS = ["f1", "motogp", "nascar", "race", "formula"]

# ================= HELPER =================
def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

def blocked(title):
    t = title.lower()
    return any(w in t for w in BLOCK_WORDS)

def is_race(title):
    t = title.lower()
    return any(w in t for w in RACE_WORDS)

def parse_time(s):
    return datetime.strptime(s[:14], "%Y%m%d%H%M%S")

# ================= LOAD M3U =================
channels = []

with open(INPUT_M3U, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

i = 0
while i < len(lines):
    if lines[i].startswith("#EXTINF"):
        info = lines[i]
        url = lines[i+1] if i+1 < len(lines) else ""

        name = info.split(",")[-1].strip()
        tvg_id = re.search(r'tvg-id="([^"]*)"', info)
        logo = re.search(r'tvg-logo="([^"]*)"', info)

        channels.append({
            "name": name,
            "key": norm(name),
            "tvg_id": tvg_id.group(1) if tvg_id else "",
            "logo": logo.group(1) if logo else "",
            "url": url
        })
        i += 2
    else:
        i += 1

# ================= LOAD EPG =================
xml = requests.get(EPG_URL, timeout=30).content
root = ET.fromstring(xml)

programs = []
for p in root.findall("programme"):
    title_el = p.find("title")
    if title_el is None:
        continue

    title = title_el.text.strip()
    if blocked(title):
        continue

    programs.append({
        "channel": p.attrib.get("channel", ""),
        "channel_key": norm(p.attrib.get("channel", "")),
        "title": title,
        "start": parse_time(p.attrib.get("start", ""))
    })

# ================= MATCH & PROCESS =================
live_channels = {}
next_events = []

for pr in programs:
    for ch in channels:
        # FUZZY MATCH (INI FIX UTAMA)
        if ch["key"] in pr["channel_key"] or pr["channel_key"] in ch["key"]:

            duration = RACE_DURATION if is_race(pr["title"]) else SOCCER_DURATION
            live_start = pr["start"] - timedelta(minutes=LIVE_EARLY_MINUTES)
            live_end   = pr["start"] + duration

            if live_start <= NOW <= live_end:
                live_channels[ch["key"]] = {
                    "channel": ch,
                    "title": pr["title"],
                    "start": pr["start"]
                }
            elif NOW < live_start:
                next_events.append({
                    "channel": ch,
                    "title": pr["title"],
                    "start": pr["start"]
                })

# sort NEXT LIVE
next_events.sort(key=lambda x: x["start"])

# ================= WRITE OUTPUT =================
today = NOW.strftime("%d %B %Y").upper()

with open(OUTPUT_M3U, "w", encoding="utf-8") as out:
    out.write(f'#EXTM3U url-tvg="{EPG_URL}"\n\n')

    # ===== LIVE NOW =====
    out.write(f"# ===== LIVE NOW {today} =====\n")
    for v in live_channels.values():
        ch = v["channel"]
        time = v["start"].strftime("%H:%M WIB")
        out.write(
            f'#EXTINF:-1 tvg-id="{ch["tvg_id"]}" '
            f'tvg-logo="{ch["logo"]}" '
            f'group-title="LIVE NOW {today}",'
            f'🔴 LIVE • {time} • {v["title"]}\n'
        )
        out.write(ch["url"] + "\n\n")

    # ===== NEXT LIVE =====
    out.write("# ===== NEXT LIVE =====\n")
    for ev in next_events:
        ch = ev["channel"]
        dt = ev["start"]
        out.write(
            f'#EXTINF:-1 tvg-id="{ch["tvg_id"]}" '
            f'tvg-logo="{ch["logo"]}" '
            f'group-title="NEXT LIVE",'
            f'{dt.strftime("%d %B %Y").upper()} • {dt.strftime("%H:%M WIB")} • {ev["title"]}\n'
        )
        out.write(ch["url"] + "\n\n")

print("OK: live_match.m3u generated (HYBRID + FUZZY MATCH)")

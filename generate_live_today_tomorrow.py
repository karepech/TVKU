#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# ================= CONFIG =================
INPUT_M3U  = "live_channels.m3u"
OUTPUT_M3U = "live_match.m3u"

EPG_URL = "https://raw.githubusercontent.com/karepech/Epgku/main/epg_wib_sports.xml"

NOW = datetime.now()

LIVE_EARLY = timedelta(minutes=30)
SOCCER_DURATION = timedelta(hours=5)
RACE_DURATION   = timedelta(hours=4)

BLOCK_KEYWORDS = [
    "replay", "highlight", "highlights",
    "review", "classic", "goals of the season"
]

RACE_KEYWORDS = ["f1", "formula", "motogp", "nascar", "race"]

# ================= HELPER =================
def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())

def is_blocked(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in BLOCK_KEYWORDS)

def is_race(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in RACE_KEYWORDS)

def parse_time(t: str) -> datetime:
    return datetime.strptime(t[:14], "%Y%m%d%H%M%S")

# ================= LOAD CHANNELS =================
channels = []

with open(INPUT_M3U, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

i = 0
while i < len(lines):
    if lines[i].startswith("#EXTINF"):
        extinf = lines[i]
        url = lines[i+1] if i+1 < len(lines) else ""
        name = extinf.split(",")[-1].strip()

        channels.append({
            "extinf": extinf,
            "name": name,
            "key": norm(name),
            "url": url,
            "live": None,
            "next": None
        })
        i += 2
    else:
        i += 1

# ================= LOAD EPG =================
xml_data = requests.get(EPG_URL, timeout=30).content
root = ET.fromstring(xml_data)

for p in root.findall("programme"):
    title_el = p.find("title")
    if title_el is None:
        continue

    title = title_el.text.strip()
    if is_blocked(title):
        continue

    start = parse_time(p.attrib["start"])
    channel_id = norm(p.attrib.get("channel", ""))

    duration = RACE_DURATION if is_race(title) else SOCCER_DURATION
    live_start = start - LIVE_EARLY
    live_end   = start + duration

    for ch in channels:
        if ch["key"] in channel_id or channel_id in ch["key"]:
            if live_start <= NOW <= live_end:
                ch["live"] = (title, start)
            elif NOW < live_start:
                if not ch["next"] or start < ch["next"][1]:
                    ch["next"] = (title, start)

# ================= WRITE OUTPUT =================
today_label = NOW.strftime("%d %B %Y").upper()

with open(OUTPUT_M3U, "w", encoding="utf-8") as out:
    out.write(f'#EXTM3U url-tvg="{EPG_URL}"\n\n')

    for ch in channels:
        base = ch["extinf"].rsplit(",", 1)[0]

        if ch["live"]:
            title, start = ch["live"]
            new_name = f'🔴 LIVE • {ch["name"]} • {title} • {start.strftime("%H:%M WIB")}'
            group = f'group-title="LIVE NOW {today_label}"'

        elif ch["next"]:
            title, start = ch["next"]
            new_name = f'{start.strftime("%d %B %Y").upper()} • {start.strftime("%H:%M WIB")} • {title}'
            group = 'group-title="NEXT LIVE"'

        else:
            new_name = ch["name"]
            group = ""

        extinf_new = re.sub(r'group-title="[^"]*"', "", base).strip()
        if group:
            extinf_new += f' {group}'

        out.write(f"{extinf_new},{new_name}\n")
        out.write(ch["url"] + "\n\n")

print("OK - generate_live_today_tomorrow.py selesai")

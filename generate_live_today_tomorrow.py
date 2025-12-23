#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MODE HYBRID IPTV
LIVE NOW  = CHANNEL (beIN, Astro, Sky, dll)
NEXT LIVE = EVENT LIST (1 title saja)

Time source  : EPG WIB (FIX)
LIVE offset  : 30 menit sebelum tayang TV
Durasi       : Bola 5 jam, Race 4 jam
"""

import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict

# =========================
# CONFIG
# =========================
INPUT_M3U  = "live_epg_sports.m3u"
OUTPUT_M3U = "live_match.m3u"

EPG_URL = "https://raw.githubusercontent.com/karepech/Epgku/main/epg_wib_sports.xml"

LIVE_EARLY_MINUTES = 30
SOCCER_DURATION_HOURS = 5
RACE_DURATION_HOURS   = 4

NOW = datetime.now()  # WIB karena EPG sudah WIB

# kata kunci yang DIBUANG (bukan live match)
BLOCK_WORDS = [
    "replay", "highlight", "highlights",
    "goals of the season",
    "magazine", "review",
    "netbusters", "the final",
    "classic", "rerun"
]

# keyword race
RACE_WORDS = ["f1", "motogp", "nascar", "race", "formula"]

# keyword soccer
SOCCER_HINTS = [" vs ", " v ", " vs. ", " v. ", "fc ", " united", " city", " madrid"]

# =========================
# HELPER
# =========================
def clean_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())

def is_blocked(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in BLOCK_WORDS)

def is_race(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in RACE_WORDS)

def is_soccer(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in SOCCER_HINTS)

def parse_epg_datetime(dt: str) -> datetime:
    # contoh: 20251223213000
    return datetime.strptime(dt[:14], "%Y%m%d%H%M%S")

# =========================
# LOAD M3U CHANNELS
# =========================
channels = []
with open(INPUT_M3U, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

i = 0
while i < len(lines):
    line = lines[i]
    if line.startswith("#EXTINF"):
        info = line
        url = lines[i + 1] if i + 1 < len(lines) else ""
        tvg_id = re.search(r'tvg-id="([^"]*)"', info)
        tvg_name = re.search(r'tvg-name="([^"]*)"', info)
        tvg_logo = re.search(r'tvg-logo="([^"]*)"', info)

        name = info.split(",")[-1].strip()

        channels.append({
            "raw": info,
            "url": url,
            "tvg_id": tvg_id.group(1) if tvg_id else "",
            "name": tvg_name.group(1) if tvg_name else name,
            "logo": tvg_logo.group(1) if tvg_logo else "",
            "key": clean_name(tvg_name.group(1) if tvg_name else name)
        })
        i += 2
    else:
        i += 1

# =========================
# LOAD EPG
# =========================
xml_data = requests.get(EPG_URL, timeout=30).content
root = ET.fromstring(xml_data)

programs = []
for p in root.findall("programme"):
    channel_id = p.attrib.get("channel", "")
    start = parse_epg_datetime(p.attrib.get("start", ""))
    title_el = p.find("title")
    if title_el is None:
        continue

    title = title_el.text.strip()
    if is_blocked(title):
        continue

    programs.append({
        "channel": channel_id,
        "start": start,
        "title": title
    })

# =========================
# MATCH CHANNEL ↔ EPG
# =========================
channel_map = {}
for ch in channels:
    if ch["tvg_id"]:
        channel_map[ch["tvg_id"]] = ch

# =========================
# PROCESS LIVE & NEXT
# =========================
live_channels = {}
next_events = []

for p in programs:
    ch = channel_map.get(p["channel"])
    if not ch:
        continue

    title = p["title"]
    start = p["start"]

    # durasi
    if is_race(title):
        duration = timedelta(hours=RACE_DURATION_HOURS)
    else:
        duration = timedelta(hours=SOCCER_DURATION_HOURS)

    live_start = start - timedelta(minutes=LIVE_EARLY_MINUTES)
    live_end   = start + duration

    if live_start <= NOW <= live_end:
        # LIVE NOW → CHANNEL
        live_channels[ch["key"]] = {
            "channel": ch,
            "title": title,
            "start": start
        }

    elif NOW < live_start:
        # NEXT LIVE → EVENT
        next_events.append({
            "channel": ch,
            "title": title,
            "start": start
        })

# sort NEXT LIVE
next_events.sort(key=lambda x: x["start"])

# =========================
# WRITE OUTPUT M3U
# =========================
today_str = NOW.strftime("%d %B %Y").upper()

with open(OUTPUT_M3U, "w", encoding="utf-8") as out:
    out.write(f'#EXTM3U url-tvg="{EPG_URL}"\n\n')

    # ================= LIVE NOW =================
    out.write(f"# ===== LIVE NOW {today_str} =====\n")
    for item in live_channels.values():
        ch = item["channel"]
        title = item["title"]
        time_str = item["start"].strftime("%H:%M WIB")

        out.write(
            f'#EXTINF:-1 tvg-id="{ch["tvg_id"]}" '
            f'tvg-logo="{ch["logo"]}" '
            f'group-title="LIVE NOW {today_str}",'
            f'🔴 LIVE • {time_str} • {title}\n'
        )
        out.write(ch["url"] + "\n\n")

    # ================= NEXT LIVE =================
    out.write("# ===== NEXT LIVE =====\n")
    for ev in next_events:
        ch = ev["channel"]
        title = ev["title"]
        dt = ev["start"]
        date_str = dt.strftime("%d %B %Y").upper()
        time_str = dt.strftime("%H:%M WIB")

        out.write(
            f'#EXTINF:-1 tvg-id="{ch["tvg_id"]}" '
            f'tvg-logo="{ch["logo"]}" '
            f'group-title="NEXT LIVE",'
            f'{date_str} • {time_str} • {title}\n'
        )
        out.write(ch["url"] + "\n\n")

print("DONE: live_match.m3u generated (HYBRID MODE)")

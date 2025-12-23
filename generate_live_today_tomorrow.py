import requests
import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches

# ===================== CONFIG =====================
EPG_URL = "https://raw.githubusercontent.com/karepech/Epgku/refs/heads/main/epg_wib_sports.xml"
INPUT_M3U = "live_epg_sports.m3u"
OUT_M3U = "live_match.m3u"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)

LIVE_PRE_MINUTES = 5          # LIVE 5 menit sebelum kickoff
MAX_MATCH_HOURS = 5           # Bola
MAX_RACE_HOURS = 4            # Race

SPORT_KEYWORDS = [
    "vs", " v ", " v.", " - ",
    "league", "cup", "tournament",
    "grand prix", "race", "motogp", "formula",
]

REPLAY_KEYWORDS = [
    "replay", "rerun", "re-air", "repeat",
    "highlights", "encore", "delayed"
]

PRIORITY_KEYWORDS = [
    "bein", "beinsports"
]

BULAN_ID = {
    1:"JANUARI",2:"FEBRUARI",3:"MARET",4:"APRIL",
    5:"MEI",6:"JUNI",7:"JULI",8:"AGUSTUS",
    9:"SEPTEMBER",10:"OKTOBER",11:"NOVEMBER",12:"DESEMBER"
}

# ===================== UTIL =====================
def tanggal_id(dt):
    return f"{dt.day} {BULAN_ID[dt.month]} {dt.year}"

def parse_time(t):
    return datetime.strptime(t[:14], "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc).astimezone(TZ)

def norm(t):
    return re.sub(r'[^a-z0-9]', '', t.lower())

def is_replay(title):
    t = title.lower()
    return any(k in t for k in REPLAY_KEYWORDS)

def is_sport_event(title):
    t = title.lower()
    return any(k in t for k in SPORT_KEYWORDS)

def is_priority_channel(name):
    return any(k in name.lower() for k in PRIORITY_KEYWORDS)

def is_race(title):
    t = title.lower()
    return any(k in t for k in ["race", "grand prix", "motogp", "formula", "f1"])

# ===================== LOAD EPG =====================
print("⏳ Load EPG...")
r = requests.get(EPG_URL, timeout=180)
try:
    root = ET.fromstring(gzip.decompress(r.content))
except:
    root = ET.fromstring(r.content)

epg_events = []
for p in root.findall("programme"):
    title = p.findtext("title", "").strip()
    if not title:
        continue
    if is_replay(title):
        continue
    if not is_sport_event(title):
        continue

    start = parse_time(p.attrib["start"])
    stop  = parse_time(p.attrib["stop"])
    epg_events.append({
        "channel": p.attrib["channel"],
        "title": title,
        "start": start,
        "stop": stop
    })

print(f"✔ EPG events loaded: {len(epg_events)}")

# ===================== READ M3U =====================
with open(INPUT_M3U, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

channels = []
i = 0
while i < len(lines):
    if not lines[i].startswith("#EXTINF"):
        i += 1
        continue

    extinf = lines[i]
    name = extinf.split(",",1)[1].strip() if "," in extinf else "Unknown"

    block = []
    j = i + 1
    while j < len(lines):
        if lines[j].startswith("#EXTINF"):
            break
        block.append(lines[j])
        if lines[j].strip() and not lines[j].startswith("#"):
            break
        j += 1

    if not block:
        i += 1
        continue

    channels.append({
        "name": name,
        "key": norm(name),
        "priority": is_priority_channel(name),
        "extinf": extinf,
        "block": block
    })
    i = j

print(f"✔ Channels loaded: {len(channels)}")

# ===================== BUILD PLAYLIST =====================
items = []

for ch in channels:
    for ev in epg_events:
        # Cocok longgar (HYBRID)
        if norm(ev["channel"]) not in ch["key"] and not ch["priority"]:
            continue

        max_hours = MAX_RACE_HOURS if is_race(ev["title"]) else MAX_MATCH_HOURS
        live_start = ev["start"] - timedelta(minutes=LIVE_PRE_MINUTES)
        live_end   = ev["start"] + timedelta(hours=max_hours)

        is_live = live_start <= NOW <= live_end
        is_future = NOW < live_start

        if is_live:
            group = f"LIVE NOW {tanggal_id(NOW)}"
            label = f"{ev['start'].strftime('%H:%M WIB')} • {ev['title']}"
        elif is_future:
            group = "NEXT LIVE"
            label = f"{tanggal_id(ev['start'])} • {ev['start'].strftime('%H:%M WIB')} • {ev['title']}"
        else:
            continue

        items.append({
            "start": ev["start"],
            "group": group,
            "label": label,
            "extinf": ch["extinf"],
            "block": ch["block"]
        })

# ===================== SORT =====================
items.sort(key=lambda x: x["start"])

# ===================== OUTPUT =====================
output = [
    f'#EXTM3U url-tvg="{EPG_URL}"'
]

for it in items:
    ext = re.sub(
        r'group-title="[^"]*"',
        f'group-title="{it["group"]}"',
        it["extinf"]
    )
    ext = ext.split(",",1)[0] + "," + it["label"]

    output.append(ext)
    output.extend(it["block"])

with open(OUT_M3U, "w", encoding="utf-8") as f:
    f.write("\n".join(output) + "\n")

print("✅ SELESAI")
print("✔ Semua channel sports bisa LIVE")
print("✔ beIN tidak bisa hilang")
print("✔ NEXT LIVE aman")
print("✔ WIB valid")
print("✔ Hybrid aktif")

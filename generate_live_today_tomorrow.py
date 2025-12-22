import requests
import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches

# ===============================
# KONFIGURASI
# ===============================
EPG_URL = "https://epg.pw/xmltv/epg.xml"
INPUT_M3U = "live_epg_sports.m3u"

OUT_NOW = "live_now.m3u"
OUT_TODAY = "live_today.m3u"
OUT_TOMORROW = "live_tomorrow.m3u"
LOG_FILE = "unmatched_channels.log"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)
TODAY = NOW.date()
TOMORROW = TODAY + timedelta(days=1)

# ===============================
# KEYWORD PERTANDINGAN
# ===============================
MATCH_KEYWORDS = [
    "VS", " V ", "MATCH", "GAME", "RACE", "FINAL", "SEMI",
    "LEAGUE", "CUP", "CHAMPIONSHIP",
    "FOOTBALL", "SOCCER", "BASKET", "NBA",
    "BADMINTON", "TENNIS", "ATP", "WTA",
    "MOTOGP", "FORMULA", "F1",
    "BOXING", "UFC", "MMA", "FIGHT"
]

BLOCK_KEYWORDS = [
    "HIGHLIGHT", "REPLAY", "PREVIEW", "REVIEW",
    "STUDIO", "ANALYSIS", "MAGAZINE",
    "DOCUMENTARY", "TALK", "SHOW", "NEWS"
]

# ===============================
# HELPER
# ===============================
def parse_time(t):
    return datetime.strptime(t[:14], "%Y%m%d%H%M%S") \
        .replace(tzinfo=timezone.utc) \
        .astimezone(TZ)

def norm(text):
    text = text.lower()
    text = re.sub(r'\b(hd|fhd|uhd|4k|live|channel)\b', '', text)
    return re.sub(r'[^a-z0-9]', '', text)

def is_live_match(title):
    t = title.upper()
    if any(b in t for b in BLOCK_KEYWORDS):
        return False
    return any(k in t for k in MATCH_KEYWORDS)

# ===============================
# DOWNLOAD EPG
# ===============================
print("📡 Download EPG...")
r = requests.get(EPG_URL, timeout=180)
try:
    content = gzip.decompress(r.content)
except:
    content = r.content

root = ET.fromstring(content)

# ===============================
# BUILD EPG CHANNEL MAP
# ===============================
epg_channel_map = {}
epg_keys = []

for ch in root.findall("channel"):
    cid = ch.attrib.get("id")
    name = ch.findtext("display-name", "")
    if cid and name:
        key = norm(name)
        epg_channel_map[key] = cid
        epg_keys.append(key)

print(f"✅ EPG channels loaded: {len(epg_channel_map)}")

# ===============================
# BUILD LIVE MATCH MAP
# ===============================
live_now = {}
live_today = {}
live_tomorrow = {}

for p in root.findall("programme"):
    cid = p.attrib.get("channel")
    start = parse_time(p.attrib["start"])
    stop = parse_time(p.attrib["stop"])
    title = p.findtext("title", "")

    if not is_live_match(title):
        continue

    if start <= NOW <= stop:
        live_now.setdefault(cid, []).append(title)

    if NOW < start and start.date() == TODAY:
        live_today.setdefault(cid, []).append((start, title))

    if start.date() == TOMORROW:
        live_tomorrow.setdefault(cid, []).append((start, title))

print("✅ LIVE MATCH filtered")

# ===============================
# BACA PLAYLIST + FUZZY tvg-id
# ===============================
with open(INPUT_M3U, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

unmatched = set()

out_now = ['#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"']
out_today = ['#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"']
out_tomorrow = ['#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"']

i = 0
while i < len(lines):
    if lines[i].startswith("#EXTINF"):
        extinf = lines[i]
        url = lines[i + 1] if i + 1 < len(lines) else ""

        m = re.search(r",([^,]+)$", extinf)
        ch_name = m.group(1) if m else ""
        ch_key = norm(ch_name)

        tvg_id = None
        m_id = re.search(r'tvg-id="([^"]+)"', extinf)
        if m_id:
            tvg_id = m_id.group(1)

        if not tvg_id and ch_key in epg_channel_map:
            tvg_id = epg_channel_map[ch_key]
            extinf = extinf.replace(
                "#EXTINF:-1",
                f'#EXTINF:-1 tvg-id="{tvg_id}"'
            )

        if not tvg_id:
            matches = get_close_matches(ch_key, epg_keys, n=1, cutoff=0.75)
            if matches:
                tvg_id = epg_channel_map[matches[0]]
                extinf = extinf.replace(
                    "#EXTINF:-1",
                    f'#EXTINF:-1 tvg-id="{tvg_id}"'
                )

        if not tvg_id:
            unmatched.add(ch_name)
        else:
            for title in live_now.get(tvg_id, []):
                out_now.append(
                    re.sub(r",.*$", f",🔴 LIVE • {title}", extinf)
                )
                out_now.append(url)

            for start, title in live_today.get(tvg_id, []):
                out_today.append(
                    re.sub(r",.*$", f",{start.strftime('%H:%M')} • {title}", extinf)
                )
                out_today.append(url)

            for start, title in live_tomorrow.get(tvg_id, []):
                out_tomorrow.append(
                    re.sub(r",.*$", f",{start.strftime('%H:%M')} • {title}", extinf)
                )
                out_tomorrow.append(url)
    i += 1

# ===============================
# SIMPAN FILE
# ===============================
for fname, data in [
    (OUT_NOW, out_now),
    (OUT_TODAY, out_today),
    (OUT_TOMORROW, out_tomorrow),
]:
    with open(fname, "w", encoding="utf-8") as f:
        f.write("\n".join(data) + "\n")

with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("❌ UNMATCHED CHANNELS\n")
    for ch in sorted(unmatched):
        f.write(f"- {ch}\n")

print("🎉 DONE: LIVE MATCH ONLY")

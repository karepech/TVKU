import requests
import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches

# ==================================================
# KONFIGURASI
# ==================================================
EPG_URL = "https://epg.pw/xmltv/epg.xml"
INPUT_M3U = "live_epg_sports.m3u"

OUT_FILE = "live_match.m3u"
LOG_FILE = "unmatched_channels.log"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)
TODAY = NOW.date()
TOMORROW = TODAY + timedelta(days=1)

LIVE_TOLERANCE_BEFORE = timedelta(minutes=15)
LIVE_TOLERANCE_AFTER = timedelta(minutes=15)

# ==================================================
# FILTER PERTANDINGAN
# ==================================================
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

# ==================================================
# HELPER
# ==================================================
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

def is_valid_epg_id(tvg_id):
    return tvg_id and not tvg_id.isdigit()

def get_stream_block(lines, start_index):
    """
    Ambil 1 BLOK STREAM UTUH:
    #EXTVLCOPT / #KODIPROP / URL
    """
    block = []
    j = start_index + 1
    while j < len(lines):
        line = lines[j].strip()
        if line.startswith("#EXTINF"):
            break
        if line:
            block.append(line)
            if not line.startswith("#"):
                break
        j += 1
    return block

# ==================================================
# DOWNLOAD & PARSE EPG
# ==================================================
print("📡 Download EPG...")
r = requests.get(EPG_URL, timeout=180)
try:
    content = gzip.decompress(r.content)
except:
    content = r.content

root = ET.fromstring(content)

# ==================================================
# BUILD MAP CHANNEL EPG
# ==================================================
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

# ==================================================
# AMBIL EVENT PERTANDINGAN
# ==================================================
events = []
for p in root.findall("programme"):
    cid = p.attrib.get("channel")
    start = parse_time(p.attrib["start"])
    stop = parse_time(p.attrib["stop"])
    title = p.findtext("title", "")

    if is_live_match(title):
        events.append((cid, start, stop, title))

print(f"✅ Match events: {len(events)}")

# ==================================================
# PROSES PLAYLIST
# ==================================================
with open(INPUT_M3U, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

output = ['#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"']
unmatched = set()

i = 0
while i < len(lines):
    if not lines[i].startswith("#EXTINF"):
        i += 1
        continue

    extinf = lines[i]
    stream_block = get_stream_block(lines, i)
    if not stream_block:
        i += 1
        continue

    # ambil nama channel
    m = re.search(r",([^,]+)$", extinf)
    ch_name = m.group(1).strip() if m else ""
    ch_key = norm(ch_name)

    # ambil tvg-id
    tvg_id = None
    m_id = re.search(r'tvg-id="([^"]*)"', extinf)
    if m_id and is_valid_epg_id(m_id.group(1)):
        tvg_id = m_id.group(1)

    if not tvg_id and ch_key in epg_channel_map:
        tvg_id = epg_channel_map[ch_key]

    if not tvg_id:
        matches = get_close_matches(ch_key, epg_keys, n=1, cutoff=0.75)
        if matches:
            tvg_id = epg_channel_map[matches[0]]

    if not tvg_id:
        unmatched.add(ch_name)
        i += 1
        continue

    # paksa sisipkan tvg-id
    if 'tvg-id=' not in extinf:
        extinf = re.sub(
            r'#EXTINF:[^ ]+',
            lambda m: f'{m.group(0)} tvg-id="{tvg_id}"',
            extinf,
            count=1
        )

    for cid, start, stop, title in events:
        if cid != tvg_id:
            continue

        # 🔴 LIVE SEKARANG
        if (start - LIVE_TOLERANCE_BEFORE) <= NOW <= (stop + LIVE_TOLERANCE_AFTER):
            new_ext = re.sub(
                r'group-title="[^"]*"',
                'group-title="LIVE SEKARANG"',
                extinf
            )
            output.append(
                re.sub(r",.*$", f",🔴 LIVE • {title}", new_ext)
            )
            output.extend(stream_block)

        # 📅 TANGGAL SEKARANG
        elif NOW < start and start.date() == TODAY:
            new_ext = re.sub(
                r'group-title="[^"]*"',
                'group-title="TANGGAL SEKARANG"',
                extinf
            )
            output.append(
                re.sub(r",.*$", f",{start.strftime('%H:%M')} • {title}", new_ext)
            )
            output.extend(stream_block)

        # 📆 TANGGAL BESOK
        elif start.date() == TOMORROW:
            new_ext = re.sub(
                r'group-title="[^"]*"',
                'group-title="TANGGAL BESOK"',
                extinf
            )
            output.append(
                re.sub(r",.*$", f",{start.strftime('%H:%M')} • {title}", new_ext)
            )
            output.extend(stream_block)

    i += 1

# ==================================================
# SIMPAN FILE
# ==================================================
with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output) + "\n")

with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("❌ UNMATCHED CHANNELS\n")
    for ch in sorted(unmatched):
        f.write(f"- {ch}\n")

print("🎉 SELESAI")
print("Output:")
print(" - live_match.m3u")
print(" - unmatched_channels.log")

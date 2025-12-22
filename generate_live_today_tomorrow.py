import requests
import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches

EPG_URL = "https://epg.pw/xmltv/epg.xml"
INPUT_M3U = "live_epg_sports.m3u"

OUT_FILE = "live_match.m3u"
LOG_FILE = "unmatched_channels.log"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)
TODAY = NOW.date()
TOMORROW = TODAY + timedelta(days=1)

LIVE_TOLERANCE_BEFORE = timedelta(minutes=15)
LIVE_TOLERANCE_AFTER = timedelta(minutes=10)

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

def parse_time(t):
    return datetime.strptime(t[:14], "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc).astimezone(TZ)

def norm(text):
    text = text.lower()
    text = text.replace("beinsports", "bein sports")
    text = text.replace("bein sport", "bein sports")
    text = re.sub(r'\b(id|uk|us|fr|de|it|es|asia|indo)\b', '', text)
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

# ================= EPG =================
r = requests.get(EPG_URL, timeout=180)
try:
    content = gzip.decompress(r.content)
except:
    content = r.content

root = ET.fromstring(content)

epg_channel_map = {}
epg_keys = []

for ch in root.findall("channel"):
    cid = ch.attrib.get("id")
    name = ch.findtext("display-name", "")
    if cid and name:
        key = norm(name)
        epg_channel_map[key] = cid
        epg_keys.append(key)

epg_events = []
for p in root.findall("programme"):
    cid = p.attrib.get("channel")
    start = parse_time(p.attrib["start"])
    stop = parse_time(p.attrib["stop"])
    title = p.findtext("title", "")
    if is_live_match(title):
        epg_events.append((cid, start, stop, title))

# ================= PLAYLIST =================
with open(INPUT_M3U, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

collected = []
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

    m = re.search(r",([^,]+)$", extinf)
    ch_name = m.group(1).strip() if m else ""
    ch_key = norm(ch_name)

    tvg_id = None
    m_id = re.search(r'tvg-id="([^"]*)"', extinf)
    if m_id and is_valid_epg_id(m_id.group(1)):
        tvg_id = m_id.group(1)

    if not tvg_id and ch_key in epg_channel_map:
        tvg_id = epg_channel_map[ch_key]

    if not tvg_id:
        matches = get_close_matches(ch_key, epg_keys, n=1, cutoff=0.6)
        if matches:
            tvg_id = epg_channel_map[matches[0]]

    if not tvg_id:
        unmatched.add(ch_name)
        i += 1
        continue

    if 'tvg-id=' not in extinf:
        extinf = re.sub(
            r'#EXTINF:[^ ]+',
            lambda m: f'{m.group(0)} tvg-id="{tvg_id}"',
            extinf, 1
        )

    for cid, start, stop, title in epg_events:
        if cid != tvg_id:
            continue

        # BUANG JIKA SUDAH LEWAT
        if NOW > (stop + LIVE_TOLERANCE_AFTER):
            continue

        if (start - LIVE_TOLERANCE_BEFORE) <= NOW <= stop:
            status = "LIVE SEKARANG"
        elif NOW < start and start.date() == TODAY:
            status = "TANGGAL SEKARANG"
        elif start.date() == TOMORROW:
            status = "TANGGAL BESOK"
        else:
            continue

        collected.append({
            "time": start,
            "status": status,
            "extinf": extinf,
            "title": title,
            "stream": stream_block
        })

    i += 1

collected.sort(key=lambda x: x["time"])

# ================= OUTPUT =================
output = ['#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"']

for item in collected:
    jam = item["time"].strftime("%H:%M")
    new_ext = re.sub(
        r'group-title="[^"]*"',
        f'group-title="{item["status"]}"',
        item["extinf"]
    )

    if item["status"] == "LIVE SEKARANG":
        output.append(
            re.sub(r",.*$", f",🔴 LIVE {jam} WIB • {item['title']}", new_ext)
        )
    else:
        output.append(
            re.sub(r",.*$", f",{jam} WIB • {item['title']}", new_ext)
        )

    output.extend(item["stream"])

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output) + "\n")

with open(LOG_FILE, "w", encoding="utf-8") as f:
    f.write("❌ UNMATCHED CHANNELS\n")
    for ch in sorted(unmatched):
        f.write(f"- {ch}\n")

print("SELESAI ✅")

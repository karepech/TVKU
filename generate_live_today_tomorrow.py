import requests, gzip, re, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches

EPG_URL = "https://epg.pw/xmltv/epg.xml"
INPUT_M3U = "live_epg_sports.m3u"
OUT_FILE = "live_match.m3u"

# ================= TIME =================
TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)

BULAN_ID = {
    1:"JANUARI",2:"FEBRUARI",3:"MARET",4:"APRIL",
    5:"MEI",6:"JUNI",7:"JULI",8:"AGUSTUS",
    9:"SEPTEMBER",10:"OKTOBER",11:"NOVEMBER",12:"DESEMBER"
}

def tanggal_id(dt):
    return f"{dt.day} {BULAN_ID[dt.month]} {dt.year}"

# ================= HELPER =================
def parse_time(t):
    return datetime.strptime(t[:14], "%Y%m%d%H%M%S") \
        .replace(tzinfo=timezone.utc) \
        .astimezone(TZ)

def norm(text):
    text = text.lower()
    text = text.replace("beinsports", "bein sports")
    text = re.sub(r'\b(id|hd|fhd|uhd|4k|asia|indo)\b', '', text)
    return re.sub(r'[^a-z0-9]', '', text)

def is_match(title):
    t = title.upper()
    if any(x in t for x in ["HIGHLIGHT","REPLAY","ANALYSIS","STUDIO"]):
        return False
    return (" VS " in t) or (" V " in t) or (" - " in t)

def detect_sport_order(channel, title):
    t = (channel + " " + title).lower()
    if any(x in t for x in ["football","soccer"," vs "," - "]):
        return 1  # Soccer
    if "badminton" in t:
        return 2
    if any(x in t for x in ["voli","volleyball"]):
        return 3
    if any(x in t for x in ["basket","nba"]):
        return 4
    if any(x in t for x in ["motogp","formula","f1"]):
        return 5
    return 9  # lainnya

def get_stream_block(lines, i):
    block = []
    j = i + 1
    while j < len(lines):
        if lines[j].startswith("#EXTINF"):
            break
        block.append(lines[j])
        if not lines[j].startswith("#"):
            break
        j += 1
    return block

# ================= LOAD EPG =================
r = requests.get(EPG_URL, timeout=180)
try:
    root = ET.fromstring(gzip.decompress(r.content))
except:
    root = ET.fromstring(r.content)

epg_channels = {}
for ch in root.findall("channel"):
    epg_channels[norm(ch.findtext("display-name",""))] = ch.attrib["id"]

epg_events = []
for p in root.findall("programme"):
    title = p.findtext("title","")
    if not is_match(title):
        continue
    epg_events.append((
        p.attrib["channel"],
        parse_time(p.attrib["start"]),
        parse_time(p.attrib["stop"]),
        title
    ))

# ================= PROCESS PLAYLIST =================
with open(INPUT_M3U, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

collected = []

i = 0
while i < len(lines):
    if not lines[i].startswith("#EXTINF"):
        i += 1
        continue

    extinf = lines[i]
    block = get_stream_block(lines, i)

    m = re.search(r",(.+)$", extinf)
    if not m:
        i += 1
        continue

    channel_name = m.group(1).strip()
    key = norm(channel_name)
    tvg_id = epg_channels.get(key)

    if not tvg_id:
        matches = get_close_matches(key, epg_channels.keys(), n=1, cutoff=0.6)
        if matches:
            tvg_id = epg_channels[matches[0]]
        else:
            i += 1
            continue

    for cid, start, stop, title in epg_events:
        if cid != tvg_id:
            continue

        if start <= NOW <= stop:
            group = f"LIVE NOW {tanggal_id(NOW)}"
        elif start > NOW:
            group = f"NEXT LIVE {tanggal_id(start)}"
        else:
            continue

        collected.append({
            "time": start,
            "sport_order": detect_sport_order(channel_name, title),
            "group": group,
            "extinf": extinf,
            "title": title,
            "block": block
        })

    i += 1

# ================= SORT =================
# 1. group (LIVE dulu otomatis karena waktunya <= NOW)
# 2. sport order (soccer, badminton, voli, dst)
# 3. jam
collected.sort(key=lambda x: (x["group"], x["sport_order"], x["time"]))

# ================= OUTPUT =================
output = ['#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"']

for e in collected:
    jam = e["time"].strftime("%H:%M WIB")
    new_ext = re.sub(
        r'group-title="[^"]*"',
        f'group-title="{e["group"]}"',
        e["extinf"]
    )
    output.append(
        re.sub(r",.*$", f",{jam} • {e['title']}", new_ext)
    )
    output.extend(e["block"])

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print("SELESAI ✅ (Urut sport tanpa title)")

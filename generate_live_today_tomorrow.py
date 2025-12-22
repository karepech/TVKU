import requests, gzip, re, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches

# ==================================================
# CONFIG
# ==================================================
EPG_URL = "https://epg.pw/xmltv/epg.xml"
INPUT_M3U = "live_epg_sports.m3u"
OUT_FILE = "live_match.m3u"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)

BULAN_ID = {
    1:"JANUARI",2:"FEBRUARI",3:"MARET",4:"APRIL",
    5:"MEI",6:"JUNI",7:"JULI",8:"AGUSTUS",
    9:"SEPTEMBER",10:"OKTOBER",11:"NOVEMBER",12:"DESEMBER"
}

def tanggal_id(dt):
    return f"{dt.day} {BULAN_ID[dt.month]} {dt.year}"

# ==================================================
# HELPERS
# ==================================================
def parse_time(t):
    return datetime.strptime(t[:14], "%Y%m%d%H%M%S") \
        .replace(tzinfo=timezone.utc) \
        .astimezone(TZ)

def norm(text):
    text = text.lower()
    text = re.sub(r'\b(id|hd|fhd|uhd|4k|asia|indo|channel)\b', '', text)
    return re.sub(r'[^a-z0-9]', '', text)

def base_channel_name(name):
    n = name.lower()
    n = re.sub(r'\b(one|two|three|four|five|main|event)\b', '', n)
    n = re.sub(r'\b\d+\b', '', n)
    n = re.sub(r'\b(id|hd|fhd|uhd|4k|asia|indo)\b', '', n)
    return re.sub(r'[^a-z0-9]', '', n)

def is_primary_channel(name):
    n = name.lower()
    return (" 1" in n) or ("one" in n) or ("main" in n)

# MODE 3: pertandingan + race + final
def is_match(title):
    t = title.upper()

    # buang non-pertandingan
    if any(x in t for x in [
        "HIGHLIGHT","REPLAY","ANALYSIS","STUDIO",
        "PRE MATCH","POST MATCH","MAGAZINE",
        "SHOW","TALK","REVIEW"
    ]):
        return False

    # pertandingan tim
    if " VS " in t or " V " in t or " - " in t:
        return True

    # race / motorsport
    if any(x in t for x in [
        "RACE","GRAND PRIX","MOTOGP","FORMULA","F1"
    ]):
        return True

    # final
    if any(x in t for x in [
        "FINAL","SEMI FINAL","QUARTER FINAL"
    ]):
        return True

    return False

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

# ==================================================
# LOAD EPG
# ==================================================
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

# ==================================================
# READ PLAYLIST
# ==================================================
with open(INPUT_M3U, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

channels = []
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

    name = m.group(1).strip()
    key = norm(name)

    tvg_id = epg_channels.get(key)
    if not tvg_id:
        matches = get_close_matches(key, epg_channels.keys(), n=1, cutoff=0.6)
        if matches:
            tvg_id = epg_channels[matches[0]]
        else:
            i += 1
            continue

    channels.append({
        "name": name,
        "base": base_channel_name(name),
        "primary": is_primary_channel(name),
        "tvg_id": tvg_id,
        "extinf": extinf,
        "block": block
    })
    i += 1

# ==================================================
# BUILD EVENTS (GLOBAL SMART MODE)
# ==================================================
collected = []

for ch in channels:
    for cid, start, stop, title in epg_events:

        # cocok langsung atau satu family nama
        same_channel = cid == ch["tvg_id"]
        same_family = base_channel_name(cid) == ch["base"]

        if not (same_channel or same_family):
            continue

        # event lewat → buang
        if NOW > stop:
            continue

        is_live = start <= NOW <= stop

        if is_live:
            group = f"LIVE NOW {tanggal_id(NOW)}"
        else:
            # NEXT LIVE hanya channel utama
            if not ch["primary"]:
                continue
            group = f"NEXT LIVE {tanggal_id(start)}"

        collected.append({
            "start": start,
            "group": group,
            "extinf": ch["extinf"],
            "title": title,
            "block": ch["block"]
        })

# ==================================================
# SORT (KUNCI BENAR)
# ==================================================
collected.sort(key=lambda x: x["start"])

# ==================================================
# OUTPUT (AMAN TANPA REGEX TITLE)
# ==================================================
output = ['#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"']

for e in collected:
    jam = e["start"].strftime("%H:%M WIB")

    new_ext = re.sub(
        r'group-title="[^"]*"',
        f'group-title="{e["group"]}"',
        e["extinf"]
    )

    # FIX REGEX ERROR: TIDAK pakai re.sub untuk title
    new_ext = new_ext.split(",", 1)[0] + f",{jam} • {e['title']}"

    output.append(new_ext)
    output.extend(e["block"])

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print("SELESAI ✅ (FULL FIXED VERSION)")

import requests, gzip, re, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches

# ================= CONFIG =================
EPG_URL = "https://epg.pw/xmltv/epg.xml"
INPUT_M3U = "live_epg_sports.m3u"
OUT_FILE = "live_match.m3u"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)

MAX_LIVE_MATCH_HOURS = 3   # ⚽ bola
MAX_LIVE_RACE_HOURS  = 4   # 🏁 race

BULAN_ID = {
    1:"JANUARI",2:"FEBRUARI",3:"MARET",4:"APRIL",
    5:"MEI",6:"JUNI",7:"JULI",8:"AGUSTUS",
    9:"SEPTEMBER",10:"OKTOBER",11:"NOVEMBER",12:"DESEMBER"
}

def tanggal_id(dt):
    return f"{dt.day} {BULAN_ID[dt.month]} {dt.year}"

# ================= HELPERS =================
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

def is_race(title):
    t = title.upper()
    return any(x in t for x in ["RACE","GRAND PRIX","MOTOGP","FORMULA","F1"])

def is_match(title):
    t = title.upper()
    if any(x in t for x in [
        "HIGHLIGHT","REPLAY","ANALYSIS","STUDIO",
        "PRE MATCH","POST MATCH","MAGAZINE",
        "SHOW","TALK","REVIEW"
    ]):
        return False
    if is_race(title):
        return True
    if any(x in t for x in ["FINAL","SEMI FINAL","QUARTER FINAL"]):
        return True
    return (" VS " in t) or (" V " in t) or (" - " in t)

# ===== STREAM BLOCK FIX =====
def get_stream_block(lines, i):
    block = []
    j = i + 1
    found_url = False

    while j < len(lines):
        line = lines[j].strip()
        if line.startswith("#EXTINF"):
            break

        block.append(lines[j])

        if line and not line.startswith("#"):
            found_url = True
            break
        j += 1

    return block if found_url else []

# ================= LOAD EPG =================
r = requests.get(EPG_URL, timeout=180)
try:
    root = ET.fromstring(gzip.decompress(r.content))
except:
    root = ET.fromstring(r.content)

epg_channels = {
    norm(ch.findtext("display-name","")): ch.attrib["id"]
    for ch in root.findall("channel")
}

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

# ================= READ PLAYLIST =================
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
    if not block:
        i += 1
        continue

    name = re.search(r",(.+)$", extinf).group(1).strip()
    key = norm(name)

    tvg_id = epg_channels.get(key)
    if not tvg_id:
        m = get_close_matches(key, epg_channels.keys(), n=1, cutoff=0.6)
        if not m:
            i += 1
            continue
        tvg_id = epg_channels[m[0]]

    channels.append({
        "name": name,
        "base": base_channel_name(name),
        "primary": is_primary_channel(name),
        "tvg_id": tvg_id,
        "extinf": extinf,
        "block": block
    })
    i += 1

# ================= BUILD EVENTS =================
collected = []

for ch in channels:
    for cid, start, stop, title in epg_events:

        if not (cid == ch["tvg_id"] or base_channel_name(cid) == ch["base"]):
            continue

        max_hours = MAX_LIVE_RACE_HOURS if is_race(title) else MAX_LIVE_MATCH_HOURS
        if NOW > start + timedelta(hours=max_hours):
            continue

        is_live = start <= NOW <= stop

        if is_live:
            group = f"LIVE NOW {tanggal_id(NOW)}"
            label = f"{start.strftime('%H:%M WIB')} • {title}"
        else:
            if not ch["primary"]:
                continue
            group = "NEXT LIVE"
            label = f"{tanggal_id(start)} • {start.strftime('%H:%M WIB')} • {title}"

        collected.append({
            "start": start,
            "group": group,
            "label": label,
            "extinf": ch["extinf"],
            "block": ch["block"]
        })

# ================= SORT =================
collected.sort(key=lambda x: x["start"])

# ================= OUTPUT (FIX FORMAT) =================
output_lines = []
output_lines.append('#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"')

for e in collected:
    ext = re.sub(
        r'group-title="[^"]*"',
        f'group-title="{e["group"]}"',
        e["extinf"]
    )
    ext = ext.split(",", 1)[0] + f",{e['label']}"

    output_lines.append(ext)

    for line in e["block"]:
        output_lines.append(line)

# 🔑 ini kunci: JOIN PAKAI NEWLINE
with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines) + "\n")

print("SELESAI ✅ FORMAT M3U SUDAH VALID")

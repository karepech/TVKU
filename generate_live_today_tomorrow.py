import requests, re, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches

# ================= CONFIG =================
EPG_URL = "https://raw.githubusercontent.com/karepech/Epgku/refs/heads/main/epg_wib_sports.xml"
INPUT_M3U = "live_epg_sports.m3u"
OUT_FILE = "live_match.m3u"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)

# ⏱️ LIVE muncul lebih awal
LIVE_EARLY_MINUTES = 30

# toleransi durasi
MAX_LIVE_MATCH_HOURS = 5   # ⚽
MAX_LIVE_RACE_HOURS  = 4   # 🏁

# 🔥 channel prioritas (tidak boleh gugur)
PRIORITY_CHANNELS = ["bein", "beinsports"]

BULAN_ID = {
    1:"JANUARI",2:"FEBRUARI",3:"MARET",4:"APRIL",
    5:"MEI",6:"JUNI",7:"JULI",8:"AGUSTUS",
    9:"SEPTEMBER",10:"OKTOBER",11:"NOVEMBER",12:"DESEMBER"
}

REPLAY_KEYWORDS = [
    "REPLAY","RERUN","RE-AIR","RE AIR","ENCORE",
    "REPEAT","DELAYED","TAPE DELAY","(R)","HIGHLIGHTS"
]

NON_MATCH_KEYWORDS = [
    "NETBUSTERS","FINAL WORD","EXTRA TIME","GENERATION",
    "MAGAZINE","STUDIO","SHOW","ANALYSIS",
    "PREVIEW","REVIEW","COUNTDOWN","HUB",
    "GOALS OF THE SEASON","FANZONE","WELCOME TO"
]

# ================= UTIL =================
def tanggal_id(dt):
    return f"{dt.day} {BULAN_ID[dt.month]} {dt.year}"

def parse_time(t):
    # EPG sudah WIB
    return datetime.strptime(t[:14], "%Y%m%d%H%M%S").replace(tzinfo=TZ)

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

def is_bein(text):
    return "bein" in text.lower()

def is_priority_channel(name):
    n = name.lower()
    return any(p in n for p in PRIORITY_CHANNELS)

def normalize_tvg_id(name, tvg_id):
    # satukan family beIN
    if is_bein(name):
        return "beinsports"
    return tvg_id

def is_race(title):
    t = title.upper()
    return any(x in t for x in ["RACE","GRAND PRIX","MOTOGP","FORMULA","F1"])

# ================= MATCH FILTER (KETAT) =================
def is_match(title):
    t = title.upper()

    if any(x in t for x in REPLAY_KEYWORDS):
        return False

    if any(x in t for x in NON_MATCH_KEYWORDS):
        return False

    if is_race(title):
        return True

    # final tanpa VS → buang
    if any(x in t for x in ["FINAL","SEMI FINAL","QUARTER FINAL"]) and " VS " not in t:
        return False

    # ⚠️ MATCH HARUS ADA VS / V
    if " VS " in t or " V " in t:
        return True

    return False

# ================= STREAM BLOCK =================
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

    tvg_id = normalize_tvg_id(name, tvg_id)

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
    for cid, start, title in epg_events:

        same_channel = cid == ch["tvg_id"]
        same_family = base_channel_name(cid) == ch["base"]
        bein_family = is_bein(cid) and is_bein(ch["name"])

        if not (same_channel or same_family or bein_family):
            continue

        max_hours = MAX_LIVE_RACE_HOURS if is_race(title) else MAX_LIVE_MATCH_HOURS

        live_start = start - timedelta(minutes=LIVE_EARLY_MINUTES)
        live_end   = start + timedelta(hours=max_hours)

        # gugur hanya jika bukan prioritas
        if NOW > live_end and not is_priority_channel(ch["name"]):
            continue

        is_live = NOW >= live_start and NOW <= live_end

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

# ================= OUTPUT =================
output = ['#EXTM3U url-tvg="{}"'.format(EPG_URL)]

for e in collected:
    ext = re.sub(
        r'group-title="[^"]*"',
        f'group-title="{e["group"]}"',
        e["extinf"]
    )
    ext = ext.split(",", 1)[0] + f",{e['label']}"

    output.append(ext)
    for line in e["block"]:
        output.append(line)

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output) + "\n")

print("SELESAI ✅ LIVE 30 MENIT LEBIH AWAL | PRIORITAS AKTIF | EPG WIB")

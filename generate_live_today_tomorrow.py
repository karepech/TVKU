import requests, gzip, re, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import get_close_matches

# ================= CONFIG =================
EPG_URL = "https://raw.githubusercontent.com/karepech/Epgku/main/epg_wib_sports.xml"
INPUT_M3U = "live_epg_sports.m3u"
OUT_FILE = "live_match.m3u"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)

LIVE_EARLY_MINUTES = 5   # ⏱ LIVE aktif 5 menit sebelum kick-off
MAX_LIVE_MATCH_HOURS = 5
MAX_LIVE_RACE_HOURS  = 4

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
    "MAGAZINE","STUDIO","SHOW","ANALYSIS",
    "PREVIEW","REVIEW","COUNTDOWN"
]

# ================= UTIL =================
def tanggal_id(dt):
    return f"{dt.day} {BULAN_ID[dt.month]} {dt.year}"

def parse_time(t):
    return datetime.strptime(t[:14], "%Y%m%d%H%M%S") \
        .replace(tzinfo=timezone.utc) \
        .astimezone(TZ)

def norm(t):
    return re.sub(r'[^a-z0-9]', '', t.lower())

def base_channel_name(n):
    n = re.sub(r'\b(one|two|three|four|five|main|event|\d+)\b', '', n.lower())
    return norm(n)

def is_primary(name):
    n = name.lower()
    return " 1" in n or "one" in n or "main" in n

def is_bein(t):
    return "bein" in t.lower()

def is_priority(name):
    return any(p in name.lower() for p in PRIORITY_CHANNELS)

def is_race(title):
    t = title.upper()
    return any(x in t for x in ["RACE","GRAND PRIX","MOTOGP","FORMULA","F1"])

def is_match(title):
    t = title.upper()
    if any(x in t for x in REPLAY_KEYWORDS): return False
    if any(x in t for x in NON_MATCH_KEYWORDS): return False
    if is_race(title): return True
    return (" VS " in t) or (" V " in t) or (" - " in t)

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

# ================= READ M3U =================
with open(INPUT_M3U, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

channels = []
i = 0
while i < len(lines):
    if not lines[i].startswith("#EXTINF"):
        i += 1
        continue

    extinf = lines[i]
    url = lines[i+1] if i+1 < len(lines) else ""
    name = re.search(r",(.+)$", extinf).group(1).strip()
    key = norm(name)

    tvg_id = epg_channels.get(key)
    if not tvg_id:
        m = get_close_matches(key, epg_channels.keys(), n=1, cutoff=0.6)
        if not m:
            i += 2
            continue
        tvg_id = epg_channels[m[0]]

    if is_bein(name):
        tvg_id = "beinsports"

    channels.append({
        "name": name,
        "base": base_channel_name(name),
        "primary": is_primary(name),
        "tvg_id": tvg_id,
        "extinf": extinf,
        "url": url
    })
    i += 2

# ================= BUILD =================
items = []

for ch in channels:
    for cid, start, stop, title in epg_events:

        if not (cid == ch["tvg_id"] or
                base_channel_name(cid) == ch["base"] or
                (is_bein(cid) and is_bein(ch["name"]))):
            continue

        max_hours = MAX_LIVE_RACE_HOURS if is_race(title) else MAX_LIVE_MATCH_HOURS

        live_start = start - timedelta(minutes=LIVE_EARLY_MINUTES)
        live_end   = start + timedelta(hours=max_hours)

        if NOW > live_end and not is_priority(ch["name"]):
            continue

        if live_start <= NOW <= live_end:
            group = f"LIVE NOW {tanggal_id(NOW)}"
            label = f"{start.strftime('%H:%M WIB')} • {title}"
        else:
            if not ch["primary"]:
                continue
            group = "NEXT LIVE"
            label = f"{tanggal_id(start)} • {start.strftime('%H:%M WIB')} • {title}"

        items.append((start, group, label, ch))

# ================= OUTPUT =================
items.sort(key=lambda x: x[0])

out = ['#EXTM3U']
for _, group, label, ch in items:
    ext = re.sub(r'group-title="[^"]*"', f'group-title="{group}"', ch["extinf"])
    ext = ext.split(",",1)[0] + f",{label}"
    out.append(ext)
    out.append(ch["url"])

with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print("✅ SELESAI | LIVE H-5 MENIT | WIB AKURAT | beIN PRIORITAS")

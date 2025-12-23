import requests, gzip, re, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

# ================= CONFIG =================
EPG_URL = "https://raw.githubusercontent.com/karepech/Epgku/refs/heads/main/epg_wib_sports.xml"
INPUT_M3U = "live_epg_sports.m3u"
OUT_M3U = "live_match.m3u"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)

LIVE_PRE_MIN = 5  # tampil LIVE 5 menit sebelum kick-off

REPLAY_KEYWORDS = [
    "REPLAY","RERUN","RE-AIR","REPEAT","HIGHLIGHT",
    "MAGAZINE","SHOW","STUDIO","ANALYSIS","PREVIEW","REVIEW"
]

# ================= UTIL =================
def norm(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())

def is_replay(title):
    t = title.upper()
    return any(x in t for x in REPLAY_KEYWORDS)

def tanggal_id(dt):
    bulan = [
        "JANUARI","FEBRUARI","MARET","APRIL","MEI","JUNI",
        "JULI","AGUSTUS","SEPTEMBER","OKTOBER","NOVEMBER","DESEMBER"
    ]
    return f"{dt.day} {bulan[dt.month-1]} {dt.year}"

# ================= LOAD EPG =================
r = requests.get(EPG_URL, timeout=120)
try:
    root = ET.fromstring(gzip.decompress(r.content))
except:
    root = ET.fromstring(r.content)

epg_events = []
for p in root.findall("programme"):
    title = p.findtext("title","").strip()
    if not title or is_replay(title):
        continue

    start = datetime.strptime(p.attrib["start"][:14], "%Y%m%d%H%M%S") \
        .replace(tzinfo=timezone.utc).astimezone(TZ)

    stop = datetime.strptime(p.attrib["stop"][:14], "%Y%m%d%H%M%S") \
        .replace(tzinfo=timezone.utc).astimezone(TZ)

    epg_events.append({
        "channel": norm(p.attrib["channel"]),
        "title": title,
        "start": start,
        "stop": stop
    })

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
    name = extinf.split(",",1)[1].strip()
    url = lines[i+1].strip()

    channels.append({
        "name": name,
        "key": norm(name),
        "extinf": extinf,
        "url": url
    })
    i += 2

# ================= BUILD OUTPUT =================
output = [f'#EXTM3U url-tvg="{EPG_URL}"']

for ch in channels:

    # cocokkan channel dengan EPG
    matches = [
        ev for ev in epg_events
        if ev["channel"] in ch["key"] or ch["key"] in ev["channel"]
    ]

    if not matches:
        continue  # ❌ tanpa EPG = tidak ditampilkan

    live_ev = None
    next_ev = None

    for ev in sorted(matches, key=lambda x: x["start"]):
        live_start = ev["start"] - timedelta(minutes=LIVE_PRE_MIN)

        if live_start <= NOW <= ev["stop"]:
            live_ev = ev
            break

        if NOW < live_start and next_ev is None:
            next_ev = ev

    if live_ev:
        new_name = (
            f"{ch['name']} | LIVE • "
            f"{live_ev['start'].strftime('%H:%M WIB')} • {live_ev['title']}"
        )
        group = f"LIVE NOW {tanggal_id(NOW)}"

    elif next_ev:
        new_name = (
            f"{ch['name']} | NEXT • "
            f"{tanggal_id(next_ev['start'])} • "
            f"{next_ev['start'].strftime('%H:%M WIB')} • {next_ev['title']}"
        )
        group = "NEXT LIVE"

    else:
        continue

    ext = re.sub(
        r'group-title="[^"]*"',
        f'group-title="{group}"',
        ch["extinf"]
    )
    ext = ext.split(",",1)[0] + "," + new_name

    output.append(ext)
    output.append(ch["url"])

# ================= SAVE =================
with open(OUT_M3U, "w", encoding="utf-8") as f:
    f.write("\n".join(output) + "\n")

print("✅ MODE SATU KESATUAN PER CHANNEL | EPG ONLY | STABIL")

import requests, gzip, re, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

# ================= CONFIG =================
EPG_URL = "https://raw.githubusercontent.com/karepech/Epgku/refs/heads/main/epg_wib_sports.xml"
INPUT_M3U = "live_epg_sports.m3u"
OUT_M3U = "live_match.m3u"

TZ = timezone(timedelta(hours=7))
NOW = datetime.now(TZ)

LIVE_PRE_MINUTES = 5
MAX_MATCH_HOURS = 5
MAX_RACE_HOURS = 4

SPORT_WORDS = ["vs", " v ", " - ", "league", "cup", "race", "motogp", "formula"]
REPLAY_WORDS = ["replay", "rerun", "highlight"]

# ================= UTIL =================
def norm(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())

def is_replay(t):
    return any(x in t.lower() for x in REPLAY_WORDS)

def is_sport(t):
    return any(x in t.lower() for x in SPORT_WORDS)

def is_race(t):
    return any(x in t.lower() for x in ["race","motogp","formula","f1"])

# ================= LOAD EPG =================
r = requests.get(EPG_URL, timeout=120)
try:
    root = ET.fromstring(gzip.decompress(r.content))
except:
    root = ET.fromstring(r.content)

events = []
for p in root.findall("programme"):
    title = p.findtext("title","").strip()
    if not title or is_replay(title) or not is_sport(title):
        continue

    start = datetime.strptime(p.attrib["start"][:14], "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc).astimezone(TZ)
    stop = datetime.strptime(p.attrib["stop"][:14], "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc).astimezone(TZ)

    events.append({
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

# ================= MATCH PER CHANNEL =================
output = [f'#EXTM3U url-tvg="{EPG_URL}"']

for ch in channels:
    matched = None

    for ev in events:
        if ev["channel"] in ch["key"] or ch["key"] in ev["channel"] or "bein" in ch["key"]:
            live_start = ev["start"] - timedelta(minutes=LIVE_PRE_MINUTES)
            max_h = MAX_RACE_HOURS if is_race(ev["title"]) else MAX_MATCH_HOURS
            live_end = ev["start"] + timedelta(hours=max_h)

            if live_start <= NOW <= live_end:
                matched = ("LIVE", ev)
                break
            if NOW < live_start and not matched:
                matched = ("NEXT", ev)

    if matched:
        mode, ev = matched
        if mode == "LIVE":
            group = "LIVE NOW"
            label = f"{ev['start'].strftime('%H:%M WIB')} • {ev['title']}"
        else:
            group = "NEXT LIVE"
            label = f"{ev['start'].strftime('%d %b %Y')} • {ev['start'].strftime('%H:%M WIB')} • {ev['title']}"
    else:
        continue

    ext = re.sub(r'group-title="[^"]*"', f'group-title="{group}"', ch["extinf"])
    ext = ext.split(",",1)[0] + "," + label

    output.append(ext)
    output.append(ch["url"])

# ================= WRITE =================
with open(OUT_M3U, "w", encoding="utf-8") as f:
    f.write("\n".join(output) + "\n")

print("✅ SELESAI | 1 CHANNEL = 1 EVENT | STABIL")

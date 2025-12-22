import xml.etree.ElementTree as ET
import requests
import gzip
import re
from datetime import datetime, timedelta, timezone

EPG_URL = "https://epg.pw/xmltv/epg.xml"
M3U_FILE = "live_epg_sports.m3u"
OUTPUT_FILE = "live_schedule.m3u"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)

def parse_time(t):
    return datetime.strptime(t[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).astimezone(TZ)

print("Download EPG...")
r = requests.get(EPG_URL, timeout=120)
try:
    content = gzip.decompress(r.content)
except:
    content = r.content

root = ET.fromstring(content)

# 1️⃣ Ambil programme LIVE
live_programmes = {}
for p in root.findall("programme"):
    cid = p.attrib.get("channel")
    start = parse_time(p.attrib["start"])
    stop = parse_time(p.attrib["stop"])

    if start <= NOW <= stop or NOW <= start <= NOW + timedelta(hours=12):
        title = p.findtext("title", default="LIVE EVENT")
        live_programmes.setdefault(cid, []).append({
            "start": start,
            "stop": stop,
            "title": title
        })

print(f"Programme live/soon: {len(live_programmes)}")

# 2️⃣ Baca playlist
with open(M3U_FILE, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

out = ['#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"']
i = 0

while i < len(lines):
    if lines[i].startswith("#EXTINF"):
        extinf = lines[i]
        url = lines[i+1] if i+1 < len(lines) else ""

        m = re.search(r'tvg-id="([^"]+)"', extinf)
        if m:
            tvg_id = m.group(1)

            if tvg_id in live_programmes:
                prog = live_programmes[tvg_id][0]
                label = f'LIVE • {prog["title"]}'
                new_extinf = re.sub(r",.*$", f",{label}", extinf)
                new_extinf = new_extinf.replace('group-title="', 'group-title="LIVE ')
                out.append(new_extinf)
                out.append(url)
    i += 1

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print(f"✅ LIVE playlist dibuat: {OUTPUT_FILE}")

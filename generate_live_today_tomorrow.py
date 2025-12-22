import requests
import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

EPG_URL = "https://epg.pw/xmltv/epg.xml"
M3U_FILE = "live_epg_sports.m3u"

OUT_TODAY = "live_today.m3u"
OUT_TOMORROW = "live_tomorrow.m3u"

TZ = timezone(timedelta(hours=7))  # WIB
NOW = datetime.now(TZ)
TODAY = NOW.date()
TOMORROW = TODAY + timedelta(days=1)

def parse_time(t):
    return datetime.strptime(t[:14], "%Y%m%d%H%M%S") \
        .replace(tzinfo=timezone.utc) \
        .astimezone(TZ)

print("Download EPG...")
r = requests.get(EPG_URL, timeout=120)
try:
    content = gzip.decompress(r.content)
except:
    content = r.content

root = ET.fromstring(content)

# ===============================
# Ambil EPG Today & Tomorrow
# ===============================
epg_map = {}

for p in root.findall("programme"):
    cid = p.attrib.get("channel")
    start = parse_time(p.attrib["start"])

    if start.date() in (TODAY, TOMORROW):
        title = p.findtext("title", "LIVE EVENT")
        epg_map.setdefault(cid, []).append({
            "title": title,
            "start": start,
            "date": start.date()
        })

print(f"EPG event ditemukan: {sum(len(v) for v in epg_map.values())}")

# ===============================
# Baca playlist
# ===============================
with open(M3U_FILE, encoding="utf-8", errors="ignore") as f:
    lines = f.read().splitlines()

today_out = ['#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"']
tomorrow_out = ['#EXTM3U url-tvg="https://epg.pw/xmltv/epg.xml"']

i = 0
while i < len(lines):
    if lines[i].startswith("#EXTINF"):
        extinf = lines[i]
        url = lines[i + 1] if i + 1 < len(lines) else ""

        m = re.search(r'tvg-id="([^"]+)"', extinf)
        if m:
            tvg_id = m.group(1)
            if tvg_id in epg_map:
                for ev in epg_map[tvg_id]:
                    label = f'{ev["start"].strftime("%H:%M")} • {ev["title"]}'
                    new_ext = re.sub(r",.*$", f",{label}", extinf)

                    if ev["date"] == TODAY:
                        today_out.append(new_ext)
                        today_out.append(url)
                    elif ev["date"] == TOMORROW:
                        tomorrow_out.append(new_ext)
                        tomorrow_out.append(url)
    i += 1

# ===============================
# Simpan hasil
# ===============================
with open(OUT_TODAY, "w", encoding="utf-8") as f:
    f.write("\n".join(today_out) + "\n")

with open(OUT_TOMORROW, "w", encoding="utf-8") as f:
    f.write("\n".join(tomorrow_out) + "\n")

print("✅ Sukses: live_today.m3u & live_tomorrow.m3u dibuat")

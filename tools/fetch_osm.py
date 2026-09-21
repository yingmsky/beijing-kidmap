#!/usr/bin/env python3
# 从 Overpass 拉取北京五环内社区级户外空间原始数据（分批 + 镜像重试）
import json, time, urllib.parse, urllib.request, os

HOSTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
UA = "liwa-map/0.1 (personal kid-map project)"

# 五环大致范围 + 近郊
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "raw1")   # 与 raw2 分开，避免同名 t*.json 互相覆盖
LAT0, LAT1 = 39.74, 40.08
LON0, LON1 = 116.04, 116.72
NT = 4   # 4x4 = 16 块

TYPES = 'leisure~"^(park|playground|garden|dog_park|skatepark|nature_reserve|pitch|sports_centre|fitness_station|swimming_area|water_park)$"'

def fetch(q, tries=3):
    body = urllib.parse.urlencode({"data": q}).encode()
    last = ""
    for i in range(tries):
        host = HOSTS[i % len(HOSTS)]
        try:
            req = urllib.request.Request(host, data=body, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=200) as r:
                t = r.read().decode("utf-8")
                if t.lstrip().startswith("{") or t.lstrip().startswith("["):
                    return json.loads(t)
                last = "非 JSON 响应: " + t[:80]
        except Exception as e:
            last = f"{host} -> {type(e).__name__}: {str(e)[:70]}"
        time.sleep(2 + i * 3)
    print("   FAIL", last)
    return None

def tiles():
    for i in range(NT):
        for j in range(NT):
            a = LAT0 + (LAT1 - LAT0) * i / NT
            b = LAT0 + (LAT1 - LAT0) * (i + 1) / NT
            c = LON0 + (LON1 - LON0) * j / NT
            d = LON0 + (LON1 - LON0) * (j + 1) / NT
            yield (a, c, b, d), f"{i}{j}"

all_elems = {}
os.makedirs(DATA, exist_ok=True)
for (s, w, n, e), tag in tiles():
    print(f"[{tag}] bbox {s:.3f},{w:.3f},{n:.3f},{e:.3f}", flush=True)
    q = f'[out:json][timeout:180];((nwr[{TYPES}]({s},{w},{n},{e});););out center tags;'
    d = fetch(q)
    if d is None:
        continue
    with open(os.path.join(DATA, f"t{tag}.json"), "w") as f:
        json.dump(d, f)
    for el in d.get("elements", []):
        uid = f"{el['type']}/{el['id']}"
        all_elems[uid] = el
    print(f"   累计 {len(all_elems)}", flush=True)
    time.sleep(1)

print("TOTAL", len(all_elems))
with open(os.path.join(DATA, "merged.json"), "w") as f:
    json.dump(list(all_elems.values()), f)

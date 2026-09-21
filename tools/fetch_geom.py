#!/usr/bin/env python3
# 第二轮：绿地多边形（算面积）+ 地铁站点（算可达）+ 树木分布（算真实树冠密度）
import json, time, urllib.parse, urllib.request, os

HOSTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
UA = "liwa-map/0.1 (personal kid-map project)"
LAT0, LAT1, LON0, LON1 = 39.74, 40.08, 116.04, 116.72
NT = 3   # 3x3 = 9 块

# 输出目录：两轮分开，避免同名 t*.json 互相覆盖
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "raw2")

def fetch(q, tries=3):
    body = urllib.parse.urlencode({"data": q}).encode()
    last = ""
    for i in range(tries):
        host = HOSTS[i % len(HOSTS)]
        try:
            req = urllib.request.Request(host, data=body, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=200) as r:
                t = r.read().decode("utf-8")
                if t.lstrip()[0] in "{[":
                    return json.loads(t)
                last = "非 JSON: " + t[:70]
        except Exception as e:
            last = f"{host} -> {type(e).__name__}: {str(e)[:60]}"
        time.sleep(3 + i * 4)
    print("   FAIL", last, flush=True)
    return None

os.makedirs(DATA, exist_ok=True)
for i in range(NT):
    for j in range(NT):
        s = LAT0 + (LAT1 - LAT0) * i / NT
        n = LAT0 + (LAT1 - LAT0) * (i + 1) / NT
        w = LON0 + (LON1 - LON0) * j / NT
        e = LON0 + (LON1 - LON0) * (j + 1) / NT
        b = f"{s},{w},{n},{e}"
        q = (
            '[out:json][timeout:200];'
            'way["leisure"~"^(park|playground|garden)$"](%s);'
            'out tags bb center;'
            'way["natural"="wood"](%s);'
            'out tags bb center;'
            'way["landuse"="forest"](%s);'
            'out tags bb center;'
            '(nwr["railway"~"^(station|halt)$"](%s);'
            'nwr["railway"="subway_entrance"](%s););'
            'out center tags;'
            '(nw["natural"="tree"](%s);nw["natural"="tree_row"](%s););'
            'out center tags;' % (b, b, b, b, b, b, b)
        )
        print(f"[{i}{j}] ", flush=True)
        d = fetch(q)
        if d:
            with open(os.path.join(DATA, f"t{i}{j}.json"), "w") as f:
                json.dump(d, f)
            print(f"    {len(d.get('elements', []))} 元素", flush=True)
        time.sleep(1)
print("done")

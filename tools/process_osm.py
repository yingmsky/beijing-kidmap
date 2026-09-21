#!/usr/bin/env python3
# 把 OSM 原始数据清洗成地图可直接用的社区点位列表
# 用法: python3 tools/process_osm.py [merged.json]
import json, math, sys, re, os, collections

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

MLAT = 111320.0
MLON = 111320.0 * math.cos(39.91 * math.pi / 180)
CORE = (39.78, 40.05, 116.10, 116.66)     # 只保留五环内

# OSM leisure -> (内部代号, 中文名)
KIND = {
    "park":            ("p", "社区公园"),
    "playground":      ("g", "儿童游乐场"),
    "garden":          ("d", "小花园 / 绿地"),
    "nature_reserve":  ("w", "林地 / 保护区"),
    "swimming_area":   ("t", "戏水 / 水边"),
    "water_park":      ("t", "戏水 / 水边"),
    "dog_park":        ("x", "遛狗 / 滑板区"),
    "skatepark":       ("x", "遛狗 / 滑板区"),
    "fitness_station": ("f", "健身器材区"),
    "pitch":           ("s", "运动场地"),
    "sports_centre":   ("s", "运动场地"),
}
# OSM 里大量「规划用地」不是真能去的地方
DROP_KW = ["地块", "用地", "拆迁", "临时", "苗圃", "变电", "项目部", "施工", "高压",
           "隔离", "防护林", "苗木", "作业道", "取土", "堆场", "弃土", "停车场用地"]
CJK = re.compile(r"[\u4e00-\u9fff]")

def in_core(lat, lon):
    return CORE[0] <= lat <= CORE[1] and CORE[2] <= lon <= CORE[3]

def dist(a, b):
    return math.hypot((a["_y"] - b["_y"]) * MLAT, (a["_x"] - b["_x"]) * MLON)

def canopy_base(lev, t):
    base = {
        "park": .50, "playground": .32, "garden": .46, "dog_park": .30, "skatepark": .03,
        "nature_reserve": .84, "pitch": .03, "sports_centre": .10,
        "fitness_station": .22, "swimming_area": .05, "water_park": .25,
    }.get(lev, .42)
    if t.get("surface") == "grass":  base -= .10
    if t.get("landcover") == "trees": base += .16
    if t.get("wood") or t.get("natural") == "wood": base += .14
    if t.get("tree_row") or t.get("trees"): base += .12
    if t.get("surface") in ("asphalt", "concrete", "paved", "paving_stones", "artificial_turf"):
        base -= .18
    return max(.03, min(.92, round(base, 2)))

def tier_of(o):
    """1 = 首选展示 2 = 次选 3 = 运动/附属，默认隐藏 0 = 丢弃"""
    n, k = o["n"], o["k"]
    if not CJK.search(n):                       # 纯英文名多半是商铺/设施
        return 3
    if any(w in n for w in DROP_KW):
        return 0
    if k == "s" and not (o["f"] & 1):           # 运动场地且无儿童设施 -> 默认收起
        return 3
    if k in ("p", "g", "w", "t") and n:
        return 1
    if k in ("d", "f", "x"):
        return 1 if n else 2
    return 1 if n else 2

def dedup(lst, radius):
    grid, keep = collections.defaultdict(list), []
    for o in lst:
        key = (int(o["_x"] * 200), int(o["_y"] * 200))
        hit = False
        for k in [(0,0),(1,0),(0,1),(1,1)]:
            for c in grid[(key[0]+k[0], key[1]+k[1])]:
                if dist(o, c) < radius:
                    c["f"] |= o["f"]
                    c["c"] = max(c["c"], o["c"])
                    hit = True
                    break
            if hit: break
        if not hit:
            grid[key].append(o)
            keep.append(o)
    return keep

ANON = {"p":"无名小绿地","d":"无名小花园","f":"小区健身区","s":"运动场地",
        "x":"空地","w":"成片林地","t":"水边","g":"无名儿童游乐场"}

def load_aux(root=os.path.join(DATA, "raw2")):
    """第二轮数据：树木分布 + 地铁出入口"""
    import glob, collections
    trees = collections.defaultdict(float)
    stations = []
    for f in glob.glob(root + "/t*.json"):
        for el in json.load(open(f)).get("elements", []):
            t = el.get("tags", {})
            c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
            if not (c.get("lat") and c.get("lon")):
                continue
            nat = t.get("natural")
            if nat == "tree":
                # 行道树成排，单棵权重低于孤植树
                trees[(int(c["lat"] / GS), int(c["lon"] / GS))] += 1
            elif nat == "tree_row":
                trees[(int(c["lat"] / GS), int(c["lon"] / GS))] += 4
            elif t.get("railway") in ("station", "halt", "subway_entrance"):
                if t.get("station") == "subway" or t.get("railway") == "subway_entrance" \
                   or t.get("subway") == "yes" or t.get("transport") == "subway":
                    stations.append((c["lat"], c["lon"]))
    return trees, stations

GS = 0.003          # 约 330m 网格
def clamp(v, a, b): return max(a, min(b, v))
TYPE_TREE_W = {"p": .70, "d": .62, "g": .52, "f": .58, "w": .80, "x": .48, "s": .25, "t": .40}

def tree_den(trees, lat, lon, R=1):
    """邻域树密度归一到 0..1（3x3 网格加权求和，中心格权重高）"""
    gi, gj = int(lat / GS), int(lon / GS)
    tot = 0.0
    for di in range(-R, R + 1):
        for dj in range(-R, R + 1):
            v = trees.get((gi + di, gj + dj), 0)
            tot += v * (1.6 if (di == 0 and dj == 0) else 1.0)
    return min(1.0, tot / 14.0), tot

def coverage(trees, lat, lon, R=2):
    """>该区域有没有人认真标过树<—— 大范围都没树只能说明数据缺失，
    不能被当成'这里没树'。北京五环内树很多，缺数据时应回落到城市均值。"""
    gi, gj = int(lat / GS), int(lon / GS)
    tot = 0.0
    for di in range(-R, R + 1):
        for dj in range(-R, R + 1):
            tot += trees.get((gi + di, gj + dj), 0)
    return min(1.0, tot / 8.0)

CITY_CANOPY = .46      # 缺数据时回落的北京五环城市均值

def metro_dist(stations, lat, lon):
    best = 1e9
    dy = lat * MLAT
    for slat, slon in stations:
        d = math.hypot((dy - slat * MLAT), (lon - slon) * MLON)
        if d < best:
            best = d
    return 99999 if best > 6000 else round(best)

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA, "raw1", "merged.json")
    raw = json.load(open(src))
    print("原始元素:", len(raw))

    trees, stations = load_aux()
    print(f"辅助数据: {len(trees)} 个含树网格 / {len(stations)} 个地铁出入口")

    named, anon = [], []
    kinds = collections.Counter()
    for el in raw:
        t = el.get("tags", {})
        lev = t.get("leisure")
        if lev not in KIND:
            if t.get("natural") == "wood" or t.get("landuse") == "forest":
                lev = "nature_reserve"
            else:
                continue
        c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        lat, lon = c.get("lat"), c.get("lon")
        if not (lat and lon) or not in_core(lat, lon):
            continue

        k, _ = KIND[lev]
        f = 0
        if lev == "playground" or t.get("playground") or t.get("slide") or t.get("swing"):
            f |= 1
        if t.get("toilets") in ("yes", "dedicated"):  f |= 2
        if t.get("drinking_water") == "yes":          f |= 4
        if t.get("lit") == "yes":                     f |= 8
        if t.get("fee") == "no":                      f |= 16
        if t.get("wheelchair") == "yes":              f |= 32
        if lev in ("swimming_area", "water_park") or t.get("natural") == "water": f |= 64
        if lev in ("pitch", "sports_centre", "skatepark"): f |= 128

        # canopy = 类型先验 ⊕ 真实行道树/树木分布（OSM natural=tree 密度）
        w = TYPE_TREE_W.get(k, .5)
        base = canopy_base(lev, t)
        dn, raw = tree_den(trees, lat, lon)
        cov = coverage(trees, lat, lon)
        est = (0.10 + 0.82 * dn) * cov + CITY_CANOPY * (1 - cov)   # 没数据就别瞎猜，回落到城市均值
        can = clamp(base * (1 - w) + est * w, .03, .93)

        o = {"n": t.get("name:zh") or t.get("name") or "", "lon": round(lon, 5),
             "lat": round(lat, 5), "k": k, "c": round(can, 2), "f": f,
             "m": metro_dist(stations, lat, lon), "nt": round(raw), "cv": round(cov, 2),
             "_x": lon, "_y": lat}
        kinds[k] += 1
        (named if o["n"] else anon).append(o)

    print("入框架前:", len(named) + len(anon), dict(kinds))
    named = dedup(named, 70)
    anon  = dedup(anon, 55)

    out = []
    for o in named + anon:
        if not o["n"]:
            o["n"] = ANON.get(o["k"], "空地")
        tr = tier_of(o)
        if tr == 0:
            continue
        o.pop("_x"); o.pop("_y")
        o["t"] = tr
        out.append(o)

    tiers = collections.Counter(o["t"] for o in out)
    print("按 tier:", dict(sorted(tiers.items())), " 合计", len(out))
    print("有游乐设施:", sum(1 for o in out if o["f"] & 1),
          " 免费:", sum(1 for o in out if o["f"] & 16),
          " 无障碍:", sum(1 for o in out if o["f"] & 32))

    out.sort(key=lambda o: (o["t"], not o["n"].startswith(("无名", "小区")), o["n"]))
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(DATA, "osm_places.js")
    js = "const OSM_PLACES = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";"
    open(dst, "w").write(js)
    print("输出:", dst, round(len(js.encode())/1024, 1), "KB")
    for o in out[:10]:
        print("  ", o["t"], o["k"], o["n"][:22], round(o["c"], 2))

main()

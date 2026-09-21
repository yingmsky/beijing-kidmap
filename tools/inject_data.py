#!/usr/bin/env python3
# 把生成的 OSM 点位注入 index.html 的 BUILD:OSM 标记之间（只动数据块，不碰样式和逻辑）
# 用法: python3 tools/inject_data.py [osm_places.js]
import re, sys, shutil, os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(HERE, "index.html")
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "data", "osm_places.js")
BACKUP = os.path.join(HERE, "index.before-inject.html")

data = open(SRC, encoding="utf-8").read().strip()
if not data.startswith("const OSM_PLACES") or not data.endswith(";"):
    sys.exit("数据源不是 OSM_PLACES 声明: " + data[:60])

# 注意：替换串必须用 lambda / \\ 转义，直接传给 re.sub 的话数据里的 \" 会被当成反斜杠引用给吃掉
html = open(HTML, encoding="utf-8").read()
new, n = re.subn(
    r"/\* BUILD:OSM:BEGIN \*/.*?/\* BUILD:OSM:END \*/",
    lambda m: "/* BUILD:OSM:BEGIN */\n" + data + "\n/* BUILD:OSM:END */",
    html, flags=re.S)
if n != 1:
    sys.exit("找不到 BUILD:OSM 标记（或不止一处）")

shutil.copyfile(HTML, BACKUP)
open(HTML, "w", encoding="utf-8").write(new)
n_items = data.count('{"n"')
print(f"注入 {n_items} 个点位，文件 {len(new.encode())/1024:.0f} KB（备份 {os.path.basename(BACKUP)}）")

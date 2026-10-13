# -*- coding: utf-8 -*-
"""把官方营养库快照注入 index.html，生成单文件可离线打开的 Demo。

数据来源与 scripts/calorie_engine.py 的 load_nutrition() 完全同源，
避免出现「Demo 数字与引擎数字不一致」这种最难查的问题。
"""
import json
import os
import re
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))   # scripts/ -> 项目根
HTML = os.path.join(ROOT, "index.html")

spec = importlib.util.spec_from_file_location(
    "ce", os.path.join(ROOT, "scripts", "calorie_engine.py"))
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)

table = ce.load_nutrition()

rows = []
for name, r in sorted(table.items(), key=lambda kv: -kv[1]["energyKcal"]):
    rows.append({
        "n": name,
        "k": int(r["energyKcal"]),
        "p": int(r["protein"]),
        "f": int(r["fat"]),
        "c": int(r["carbohydrate"]),
        "s": int(r["sodium"]),
    })

payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))

with open(HTML, "r", encoding="utf-8") as fh:
    html = fh.read()

if "__NUTRITION_DATA__" in html:
    html = html.replace("__NUTRITION_DATA__", payload)
    mode = "首次注入"
else:
    # 已是构建产物：用正则替换掉旧数据块，保证脚本可重复运行。
    # 官方随时可能改营养库，改完数据重跑本脚本即可刷新 Demo。
    pattern = re.compile(r"const NUTRITION = \[.*?\];", re.S)
    if not pattern.search(html):
        print("❌ 既没有占位符，也找不到已注入的数据块")
        sys.exit(1)
    html = pattern.sub(lambda m: "const NUTRITION = %s;" % payload, html, count=1)
    mode = "刷新数据"

with open(HTML, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(html)

size = os.path.getsize(HTML)
print("✅ %s完成" % mode)
print("   商品数 : %d 条" % len(rows))
print("   数据体积: %.1f KB" % (len(payload.encode("utf-8")) / 1024))
print("   HTML 总大小: %.1f KB" % (size / 1024))

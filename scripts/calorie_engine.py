#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcd-what-you-ate 换算引擎
==========================
把麦当劳餐品的热量，翻译成"爬多少层楼 / 跑多久 / 深蹲多少次"这类有画面感的人话。

设计原则
--------
1. 所有换算系数基于公开运动生理学 MET 值，可复算、可验证，不编造。
2. 只做"翻译"，不做"评判"——输出永远带正向的运动出口（还债方案）。
3. 结果仅作运动量参考，不构成营养或医疗建议。

用法
----
    python calorie_engine.py 巨无霸 中薯条
    python calorie_engine.py --kcal 1003
    python calorie_engine.py 巨无霸 --weight 75 --json
"""

import argparse
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------- 常量

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         os.pardir, "data", "nutrition_raw.csv")

DEFAULT_WEIGHT_KG = 60.0

# 运动 MET 值（代谢当量）。1 MET ≈ 1 kcal / (kg × 小时)
MET_TABLE = {
    "爬楼梯": 8.8,
    "跑步": 8.0,
    "跳绳": 10.0,
    "深蹲": 5.0,
    "快走": 4.3,
    "骑车": 7.5,
}

# 单位换算基准
FLOOR_HEIGHT_M = 3.0        # 一层楼约 3 米
SECONDS_PER_FLOOR = 12.0    # 一般人爬一层约 12 秒
SQUATS_PER_MIN = 30.0       # 一般人深蹲每分钟约 30 次
RICE_BOWL_KCAL = 174.0      # 一碗白米饭（150g 熟饭）约 174 kcal
SUGAR_CUBE_KCAL = 16.0      # 一块方糖（4g）约 16 kcal
OIL_SPOON_KCAL = 90.0       # 一汤匙油（10g）约 90 kcal
APPLE_KCAL = 52.0           # 一个苹果（100g 可食部）约 52 kcal

# 地标高度（米），用于"你爬的楼有多高"的参照
LANDMARKS = [
    ("深圳平安金融中心", 599),
    ("广州塔", 600),
    ("上海中心大厦", 632),
    ("珠穆朗玛峰", 8848),
]

# 段位：上界（不含）-> 段位名。按单次摄入总热量划分。
RANKS: List[Tuple[float, str]] = [
    (300, "青铜麦友"),
    (600, "白银麦友"),
    (900, "黄金麦友"),
    (1300, "铂金麦友"),
    (2000, "钻石麦友"),
    (float("inf"), "王者巨无霸"),
]

# 常见别名 -> 官方营养库商品名，解决菜单名与营养库名称口径不一致的问题
ALIASES = {
    "巨无霸汉堡": "巨无霸",
    "big mac": "巨无霸",
    "大薯": "大薯条",
    "中薯": "中薯条",
    "小薯": "小薯条",
    "薯条": "中薯条",
    "板烧": "板烧鸡腿堡",
    "板烧鸡腿汉堡": "板烧鸡腿堡",
    "麦辣鸡腿堡": "麦辣鸡腿汉堡",
    "麦辣堡": "麦辣鸡腿汉堡",
    # ⚠️ 安格斯系列有 4 款口味/层数组合，热量差最多 296 kcal。
    # 别名必须写到「层数 + 口味」粒度，否则会静默算错（详见 --doctor 基准项）。
    "双层安格斯厚牛堡": "芝士双层安格斯厚牛堡",
    "芝士双层安格斯": "芝士双层安格斯厚牛堡",
    "培根双层安格斯": "培根双层安格斯厚牛堡",
    "双层安格斯": "芝士双层安格斯厚牛堡",
    "芝士安格斯": "芝士安格斯厚牛堡",
    "培根安格斯": "培根安格斯厚牛堡",
    "双层牛堡": "芝士双层安格斯厚牛堡",
    "安格斯": "芝士安格斯厚牛堡",
    "可乐": "可乐中杯",
    "雪碧": "雪碧中杯",
    "麦旋风": "奥利奥麦旋风",
    "圆筒": "圆筒冰淇淋",
    "甜筒": "圆筒冰淇淋",
    "麦乐鸡": "麦乐鸡5块",
    "咖啡": "大杯鲜萃咖啡",
    "鲜萃": "大杯鲜萃咖啡",
    "无糖可乐": "无糖可口可乐中杯",
    "零度": "无糖可口可乐中杯",
    "牛奶": "纯牛奶（盒装）",
    "豆浆": "优品豆浆大杯",
    "苹果汁": "100%苹果汁",
}


# ---------------------------------------------------------------- 数据层

def load_nutrition(path: str = DATA_FILE) -> Dict[str, dict]:
    """读取官方营养库快照，返回 {商品名: 营养字典}。

    数据来源：麦当劳 MCP `list-nutrition-foods`（本仓库 data/nutrition_raw.csv）。
    同名商品若重复出现，保留首次出现的记录。
    """
    if not os.path.exists(path):
        raise FileNotFoundError("找不到营养数据文件：%s" % path)

    items: Dict[str, dict] = {}
    with open(path, "r", encoding="utf-8") as fh:
        header = fh.readline().strip().lstrip("\ufeff").split(",")
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != len(header):
                continue
            row = dict(zip(header, parts))
            name = row["productName"].strip()
            if not name or name in items:
                continue
            try:
                row["energyKcal"] = float(row["energyKcal"])
                row["energyKj"] = float(row["energyKj"])
                row["protein"] = float(row["protein"])
                row["fat"] = float(row["fat"])
                row["carbohydrate"] = float(row["carbohydrate"])
                row["sodium"] = float(row["sodium"])
                row["calcium"] = float(row["calcium"])
            except ValueError:
                continue
            if row["nutritionDescription"] == "null":
                row["nutritionDescription"] = None
            items[name] = row
    return items


def resolve_name(query: str, items: Dict[str, dict]) -> Optional[str]:
    """把用户口语化的叫法解析成营养库里的正式商品名。"""
    q = str(query or "").strip()
    # ⚠️ 空查询必须在这里拦掉，不能落到下面的子串兜底。
    # 因为 "" in n 对**任何**字符串都为真，空输入会静默命中"最短的商品名"
    # （实际是「纯悦」，0 kcal），用户会看到一张完全不属于自己的账单。
    # JS 侧有多年来一直写对的 `if (!q) return null`，此处补齐以保证两引擎行为一致。
    if not q:
        return None
    if q in items:
        return q
    low = q.lower()
    if low in ALIASES and ALIASES[low] in items:
        return ALIASES[low]
    # 按别名长度降序匹配：更具体的别名优先。
    # ⚠️ 顺序不能反 —— 否则「双层安格斯」会被更短的「安格斯」抢先命中，
    # 静默算成另一款产品（曾导致少算 296 kcal / 42% 误差）。
    for alias, target in sorted(ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if alias.lower() in low and target in items:
            return target
    # 退化为子串匹配，取最短的（通常最贴近原意）
    hits = [n for n in items if q in n]
    if hits:
        return sorted(hits, key=len)[0]
    hits = [n for n in items if n in q]
    if hits:
        return sorted(hits, key=len, reverse=True)[0]
    return None


# ---------------------------------------------------------------- 换算层

def met_kcal_per_min(met: float, weight_kg: float) -> float:
    """MET -> 每分钟消耗千卡。"""
    return met * weight_kg / 60.0


def safe_weight(weight_kg: float) -> float:
    """把非法体重收敛成可用的数值。

    ⚠️ 为什么在 convert 里收敛而不是抛异常：convert 的铁律是**键集合恒定**，
    一旦抛异常，调用方连字段都拿不到。所以这里静默收敛，由 CLI 层
    （main 的 --weight 校验）负责向用户明确报错 —— 双层防御。

    触发场景：0（除零崩溃）、负数（得出负的爬楼层数）、nan/inf（污染全表）。
    """
    try:
        w = float(weight_kg)
    except (TypeError, ValueError):
        return DEFAULT_WEIGHT_KG
    if not math.isfinite(w) or w <= 0:
        return DEFAULT_WEIGHT_KG
    return w


def convert(kcal: float, weight_kg: float = DEFAULT_WEIGHT_KG) -> dict:
    """把热量翻译成各类生活化当量。

    ⚠️ 铁律：无论热量是否为 0，返回的键集合必须**完全一致**。
    调用方（Skill 与 JSON 消费端）依赖固定字段，任何提前 return 都会
    让下游拿不到字段而 KeyError —— 这是本项目已修复过的真实 bug。
    零热量时各字段自然为 0，并额外给出 zero=True 供展示层判断。
    """
    weight_kg = safe_weight(weight_kg)
    stairs_kcal_min = met_kcal_per_min(MET_TABLE["爬楼梯"], weight_kg)

    out: dict = {
        "爬楼层数": kcal / (stairs_kcal_min * SECONDS_PER_FLOOR / 60.0),
        "爬楼分钟": kcal / stairs_kcal_min,
    }
    out["爬楼高度米"] = out["爬楼层数"] * FLOOR_HEIGHT_M

    for key, met in (("跑步分钟", "跑步"), ("跳绳分钟", "跳绳"),
                     ("快走分钟", "快走"), ("骑车分钟", "骑车")):
        out[key] = kcal / met_kcal_per_min(MET_TABLE[met], weight_kg)

    out["深蹲次数"] = kcal / (met_kcal_per_min(MET_TABLE["深蹲"], weight_kg) / SQUATS_PER_MIN)

    out["白米饭碗数"] = kcal / RICE_BOWL_KCAL
    out["方糖块数"] = kcal / SUGAR_CUBE_KCAL
    out["食用油汤匙"] = kcal / OIL_SPOON_KCAL
    out["苹果个数"] = kcal / APPLE_KCAL

    out["zero"] = kcal <= 0
    return out


def landmark_note(height_m: float) -> Optional[str]:
    """给出"比你爬的楼还矮"的地标参照，制造荒诞感。"""
    if height_m <= 0:
        return None
    for name, h in LANDMARKS:
        if height_m >= h:
            ratio = height_m / h
            return "约等于 %.0f 个%s叠起来那么高" % (ratio, name)
    return None


def rank_of(kcal: float) -> str:
    for upper, name in RANKS:
        if kcal < upper:
            return name
    return RANKS[-1][1]


def payoff_plans(kcal: float, weight_kg: float = DEFAULT_WEIGHT_KG) -> List[str]:
    """还债方案——三选一的可执行运动出口（正向引导，不给负罪感）。"""
    c = convert(kcal, weight_kg)
    if c.get("zero"):
        return ["这顿热量接近于零，你什么都不欠。"]
    return [
        "爬楼梯 %.0f 分钟（约 %.0f 层）" % (c["爬楼分钟"], c["爬楼层数"]),
        "慢跑 %.0f 分钟" % c["跑步分钟"],
        "跳绳 %.0f 分钟" % c["跳绳分钟"],
    ]


# ---------------------------------------------------------------- 展示层

def render(items: List[dict], weight_kg: float = DEFAULT_WEIGHT_KG) -> str:
    """渲染成人话账单。"""
    total = sum(i["kcal"] for i in items)
    total_nut = {
        "protein": sum(i["protein"] for i in items),
        "fat": sum(i["fat"] for i in items),
        "carbohydrate": sum(i["carbohydrate"] for i in items),
        "sodium": sum(i["sodium"] for i in items),
    }
    c = convert(total, weight_kg)
    rank = rank_of(total)

    lines: List[str] = []
    lines.append("## 你这一单，到底吃了什么")
    lines.append("")
    lines.append("| 餐品 | 热量(kcal) | 蛋白质(g) | 脂肪(g) | 碳水(g) |")
    lines.append("|---|---:|---:|---:|---:|")
    for i in items:
        lines.append("| %s | %.0f | %.0f | %.0f | %.0f |" % (
            i["name"], i["kcal"], i["protein"], i["fat"], i["carbohydrate"]))
    lines.append("| **合计** | **%.0f** | **%.0f** | **%.0f** | **%.0f** |" % (
        total, total_nut["protein"], total_nut["fat"], total_nut["carbohydrate"]))
    lines.append("")
    lines.append("## 翻译成人话")
    lines.append("")
    lines.append("> **%.0f kcal**，按 %s 体重换算 —— 段位：**%s**" % (
        total, ("%.0fkg" % weight_kg), rank))

    if c.get("zero"):
        lines.append(">")
        lines.append("> 🫥 这一单热量接近于零。楼也不用爬了，今天你赢麻了。")
    else:
        lines.append(">")
        lines.append("> 🏢 要爬 **%.0f 层楼**（约 %.0f 分钟，爬升 %.0f 米）" % (
            c["爬楼层数"], c["爬楼分钟"], c["爬楼高度米"]))
        lines.append("> 🏃 或者跑步 **%.0f 分钟**" % c["跑步分钟"])
        lines.append("> 🦵 或者深蹲 **%.0f 次**" % c["深蹲次数"])
        lines.append("> 🍚 或者 **%.1f 碗白米饭** / **%.0f 块方糖** / **%.1f 汤匙油**" % (
            c["白米饭碗数"], c["方糖块数"], c["食用油汤匙"]))

        lm = landmark_note(c["爬楼高度米"])
        if lm:
            lines.append(">")
            lines.append("> 📐 你爬的这栋楼高 %.0f 米 —— %s" % (c["爬楼高度米"], lm))

    lines.append("")
    lines.append("## 怎么还（三选一）")
    lines.append("")
    for i, plan in enumerate(payoff_plans(total, weight_kg), 1):
        lines.append("%d. %s" % (i, plan))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("热量数据来自麦当劳官方 MCP（list-nutrition-foods），非估算值。")
    lines.append("运动当量按 %.0fkg 成人 MET 值换算，仅作运动量参考，不构成营养或医疗建议。" % weight_kg)
    return "\n".join(lines)


# ---------------------------------------------------------------- 自检

def doctor(table: Dict[str, dict]) -> int:
    """自检：数据一致性 + 名称解析 + 边界安全 + 基准防回归。

    设计意图：营养库是从官方 MCP 拉取的快照，官方随时可能改名/下架商品；
    别名表也是人工维护的。两者一旦不同步，用户就会拿到**错误但看起来正常**的热量。
    本自检把这类静默错误变成显式失败，返回码非 0 即表示有需修复的问题。
    """
    checks: List[Tuple[str, bool, str]] = []

    checks.append(("营养库加载", len(table) > 100, "%d 条商品" % len(table)))

    bad_alias = [(k, v) for k, v in ALIASES.items() if v not in table]
    checks.append(("别名表目标均存在", not bad_alias,
                   "共 %d 条别名，全部命中" % len(ALIASES) if not bad_alias
                   else "指向不存在商品：%s" % bad_alias))

    self_bad = [n for n in table if resolve_name(n, table) != n]
    checks.append(("库内条目自解析唯一", not self_bad,
                   "%d 条全部自洽" % len(table) if not self_bad
                   else "解析串味：%s" % self_bad[:5]))

    alias_fail = [k for k in ALIASES if resolve_name(k, table) is None]
    checks.append(("别名全部可解析", not alias_fail,
                   "全部可用" if not alias_fail else "无法解析：%s" % alias_fail[:5]))

    keys_hot, keys_zero = set(convert(800).keys()), set(convert(0).keys())
    checks.append(("零热量返回字段完整", keys_hot == keys_zero,
                   "字段一致（%d 个）" % len(keys_hot) if keys_hot == keys_zero
                   else "零热量缺少：%s" % (keys_hot - keys_zero)))

    # 空查询会把 "" 当成子串命中**任意**商品（"" in n 恒为真），
    # 静默返回一张不属于用户的账单。必须返回 None。
    blank_ok = all(resolve_name(q, table) is None for q in ("", " ", "\t", "\n", "  \t "))
    checks.append(("空查询不误命中商品", blank_ok,
                   "空/纯空白查询全部返回 None" if blank_ok
                   else "空查询命中了：%s" % [resolve_name(q, table) for q in ("", " ", "\t")]))

    # 非法体重（0/负数/nan）曾导致除零崩溃与负的爬楼层数
    try:
        base = convert(500, DEFAULT_WEIGHT_KG)
        bad_w = [convert(500, w) for w in (0, -60, float("nan"))]
        weight_ok = all(
            set(b.keys()) == set(base.keys())
            and abs(b["爬楼层数"] - base["爬楼层数"]) < 1e-9
            for b in bad_w)
        detail = "0/负数/nan 均收敛为默认体重且不崩" if weight_ok else "未正确收敛"
    except Exception as e:                                  # noqa: BLE001
        weight_ok, detail = False, "%s: %s" % (type(e).__name__, e)
    checks.append(("非法体重安全收敛", weight_ok, detail))

    # 基准用例：数字一旦漂移，说明数据或换算被改坏
    baseline = [
        ("巨无霸", 513.0),
        ("双层安格斯厚牛堡", 1003.0),   # 曾因短别名"安格斯"抢先而错算成 707
        ("大薯", 379.0),
        ("无糖可口可乐中杯", 0.0),
    ]
    for query, expect in baseline:
        resolved = resolve_name(query, table)
        got = table[resolved]["energyKcal"] if resolved else None
        checks.append(("基准 %s = %.0f kcal" % (query, expect), got == expect,
                       "实际 %s" % ("%.0f" % got if got is not None else "解析失败")))

    total_kcal = sum(table[r]["energyKcal"] for r in ("巨无霸", "中薯条"))
    checks.append(("基准合计 巨无霸+中薯条 = 802 kcal", total_kcal == 802.0,
                   "实际 %.0f" % total_kcal))

    width = max(len(name) for name, _, _ in checks)
    for name, ok, detail in checks:
        print("%s %-*s  %s" % ("✅" if ok else "❌", width, name, detail))

    failed = [name for name, ok, _ in checks if not ok]
    print()
    if failed:
        print("❌ 自检未通过：%d / %d 项失败 → %s" % (len(failed), len(checks), "、".join(failed)))
        return 1
    print("✅ 全部 %d 项自检通过。" % len(checks))
    return 0


# ---------------------------------------------------------------- 入口

def build_records(names: List[str], items: Dict[str, dict]) -> Tuple[List[dict], List[str]]:
    records, missing = [], []
    for raw in names:
        resolved = resolve_name(raw, items)
        if not resolved:
            missing.append(raw)
            continue
        row = items[resolved]
        records.append({
            "name": resolved,
            "query": raw,
            "kcal": row["energyKcal"],
            "protein": row["protein"],
            "fat": row["fat"],
            "carbohydrate": row["carbohydrate"],
            "sodium": row["sodium"],
        })
    return records, missing


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="把麦当劳餐品的热量翻译成人话（爬楼/跑步/深蹲）")
    ap.add_argument("items", nargs="*", help="餐品名，可多个")
    ap.add_argument("--kcal", type=float, help="直接指定总热量，绕过餐品查询")
    ap.add_argument("--weight", type=float, default=DEFAULT_WEIGHT_KG,
                    help="体重(kg)，默认 60")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--list", action="store_true", help="列出营养库全部餐品")
    ap.add_argument("--doctor", action="store_true",
                    help="自检：营养库与别名表一致性、基准防回归")
    args = ap.parse_args(argv)

    # ⚠️ 体重必须**显式报错**，不能静默兜底：
    # 0 会让换算除零崩溃，负数会算出"负的爬楼层数"这种无意义结果。
    # 静默修正成默认值更坏 —— 用户会拿到一个看起来完全正常的错数字。
    if not math.isfinite(args.weight) or args.weight <= 0:
        ap.error("--weight 必须是大于 0 的数值（收到 %r）" % args.weight)
    if not 25 <= args.weight <= 350:
        print("⚠️  体重 %.1fkg 超出常见范围（25–350kg），请确认输入无误。" % args.weight,
              file=sys.stderr)

    table = load_nutrition()

    if args.doctor:
        return doctor(table)

    if args.list:
        print("营养库共 %d 条：" % len(table))
        for n, r in sorted(table.items(), key=lambda kv: -kv[1]["energyKcal"]):
            print("  %-28s %5.0f kcal" % (n, r["energyKcal"]))
        return 0

    if args.kcal is not None:
        records = [{"name": "手动指定合计", "query": "-", "kcal": args.kcal,
                    "protein": 0, "fat": 0, "carbohydrate": 0, "sodium": 0}]
        missing = []
    elif args.items:
        records, missing = build_records(args.items, table)
        if not records:
            # 全是空白输入时 missing 里是空串，直接 join 会打印出 "没认出来：[]"，
            # 用户看不懂。分开提示。
            blanks = [x for x in missing if not str(x).strip()]
            if len(blanks) == len(missing):
                print("请提供至少一个餐品名（收到的参数是空的）。", file=sys.stderr)
                print("示例：python calorie_engine.py 巨无霸 中薯条", file=sys.stderr)
            else:
                print("没认出来：%s" % "、".join(
                    x for x in missing if str(x).strip()), file=sys.stderr)
                print("提示：用 --list 看看营养库里有什么。", file=sys.stderr)
            return 2
    else:
        ap.print_help()
        return 1

    if args.json:
        total = sum(r["kcal"] for r in records)
        print(json.dumps({
            "items": records,
            "totalKcal": total,
            "rank": rank_of(total),
            "conversion": convert(total, args.weight),
            "payoff": payoff_plans(total, args.weight),
            "unmatched": missing,
        }, ensure_ascii=False, indent=2))
        return 0

    print(render(records, args.weight))
    if missing:
        print()
        print("⚠️ 这些没认出来，已跳过：%s" % "、".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())

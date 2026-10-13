# -*- coding: utf-8 -*-
"""对抗性压力测试：专门去戳 calorie_engine.py 的软肋。

设计意图：回归测试只能证明"没修坏"，证明不了"没别的问题"。
本脚本用极端参数、空输入、重复项、畸形输入去撞边界，找**静默错误**。

本脚本在 2026-10-13 首次运行即挖出两个真实缺陷（均已修复并固化为
--doctor 自检项）：
  1. 空/纯空白查询命中「纯悦」—— "" 是任意字符串的子串，静默返回错误账单
  2. --weight 0 触发 ZeroDivisionError 崩溃；负数则算出负的爬楼层数

用法：
    python stress_test.py          # 退出码非 0 表示发现需修复的问题
"""
import importlib.util
import io
import os
import sys
import traceback
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "calorie_engine.py")

spec = importlib.util.spec_from_file_location("ce", ENGINE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

TABLE = m.load_nutrition()

fails = []
warns = []


def case(title, fn, expect_error=False):
    """跑一个用例，捕获所有异常。

    expect_error=True 表示"应当被明确拒绝"：抛异常、sys.exit(非0)、
    返回非0退出码，三者都算通过；返回 0 才算失败。
    """
    try:
        out = fn()
        if expect_error:
            if isinstance(out, int) and out != 0:
                print("  ✅ %-44s 按预期拒绝（退出码 %s）" % (title, out))
            else:
                fails.append("%s —— 期望被拒绝但成功返回：%r" % (title, out))
                print("  ❌ %-44s 期望拒绝，却成功返回" % title)
        else:
            print("  ✅ %-44s %s" % (title, (str(out)[:52])))
    except SystemExit as e:
        # argparse 参数校验失败会 sys.exit(2)，这是**正确**行为
        code = e.code if isinstance(e.code, int) else 1
        if expect_error and code != 0:
            print("  ✅ %-44s 按预期拒绝（退出码 %s）" % (title, code))
        else:
            fails.append("%s —— 非预期退出，退出码 %s" % (title, code))
            print("  💥 %-44s 非预期退出，退出码 %s" % (title, code))
    except ZeroDivisionError as e:
        fails.append("%s —— ZeroDivisionError: %s" % (title, e))
        print("  💥 %-44s 除零崩溃: %s" % (title, e))
    except (KeyError, IndexError) as e:
        fails.append("%s —— %s: %s" % (title, type(e).__name__, e))
        print("  💥 %-44s %s: %s" % (title, type(e).__name__, e))
    except Exception as e:
        if expect_error:
            print("  ✅ %-44s 按预期报错(%s)" % (title, type(e).__name__))
        else:
            fails.append("%s —— %s: %s" % (title, type(e).__name__, e))
            print("  💥 %-44s %s: %s" % (title, type(e).__name__, e))


def cli(args):
    """直接调 main()，返回退出码。stdout 静默。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return m.main(args)


print("=" * 68)
print("A. 参数边界：体重")
print("=" * 68)
case("weight=0（曾除零崩溃）", lambda: cli(["--kcal", "500", "--weight", "0"]), expect_error=True)
case("weight=-60（负数）", lambda: cli(["--kcal", "500", "--weight", "-60"]), expect_error=True)
case("weight=0.0001（极小）", lambda: cli(["--kcal", "500", "--weight", "0.0001"]))
case("weight=1e9（极大）", lambda: cli(["--kcal", "500", "--weight", "1000000000"]))
case("weight=nan", lambda: cli(["--kcal", "500", "--weight", "nan"]), expect_error=True)
case("weight=abc（非数字）", lambda: cli(["--kcal", "500", "--weight", "abc"]), expect_error=True)

print()
print("=" * 68)
print("B. 参数边界：热量")
print("=" * 68)
case("kcal=-100（负数）", lambda: cli(["--kcal", "-100"]))
case("kcal=0", lambda: cli(["--kcal", "0"]))
case("kcal=1e12（天文数字）", lambda: cli(["--kcal", "1e12"]))
case("kcal=nan", lambda: cli(["--kcal", "nan"]))

print()
print("=" * 68)
print("C. 输入清洗：空值 / 空白 / 重复")
print("=" * 68)
case("空字符串参数", lambda: cli([""]), expect_error=True)
case("纯空格参数", lambda: cli(["   "]), expect_error=True)
case("制表符参数", lambda: cli(["\t\n"]), expect_error=True)
case("重复同一餐品 x3", lambda: len(m.build_records(["巨无霸"] * 3, TABLE)[0]))
case("大小写混排 BIG MAC / big mac", lambda: [m.resolve_name(x, TABLE) for x in ["BIG MAC", "big mac", "Big Mac"]])
case("前后带空格「 巨无霸 」", lambda: m.resolve_name(" 巨无霸 ", TABLE))
case("全角括号「巨无霸」", lambda: m.resolve_name("巨无霸（）", TABLE))

print()
print("=" * 68)
print("D. 转换函数结构完整性")
print("=" * 68)
for name, val in [("0", 0), ("负数", -500), ("极小正数", 0.001), ("nan", float("nan")), ("inf", float("inf"))]:
    c = m.convert(val)
    keys = len(c)
    ok = keys == 13 and all(isinstance(v, (int, float)) for v in c.values())
    flag = "✅" if ok else "❌"
    if not ok:
        fails.append("convert(%s) 字段异常：%d 个字段 %r" % (name, keys, c))
    print("  %s convert(%-6s) 字段 %d 个 %s" % (flag, name, keys, "" if ok else "← 含非数值或数量不对"))

print()
print("=" * 68)
print("E. 段位边界（跨越每一档）")
print("=" * 68)
ranks = {}
for k in [0, 1, 99, 100, 199, 200, 299, 300, 399, 400, 499, 500, 699, 700, 999, 1000, 1499, 1500, 2000, 5000]:
    r = m.rank_of(k)
    ranks.setdefault(r, []).append(k)
    print("  %-6d kcal → %s" % (k, r))
print("  → 共 %d 档：%s" % (len(ranks), " / ".join(ranks.keys())))
if not all(m.rank_of(k) for k in [0, 500, 2000]):
    fails.append("段位在边界返回空值")

print()
print("=" * 68)
print("F. 地标参照（爬升高度换算）")
print("=" * 68)
for h in [0, 1, 10, 100, 500, 598, 599, 600, 1367, 10000, 100000]:
    try:
        lm = m.landmark_note(h)   # 返回 str 或 None
        print("  %-8d 米 → %s" % (h, lm if lm else "（无参照）"))
    except Exception as e:
        fails.append("landmark_note(%s) 崩溃：%s" % (h, e))
        print("  💥 %-8d 米 → %s: %s" % (h, type(e).__name__, e))
# 覆盖性检查：低于最低地标的高度全部拿不到参照
no_lm = [h for h in [100, 300, 500, 598] if m.landmark_note(h) is None]
if no_lm:
    warns.append("爬升 %s 米以下没有地标参照（最低地标 599 米），轻食订单会缺这块内容" % max(no_lm))
    print("  ⚠️  爬升 ≤%d 米时无参照 —— 轻食订单（如吉士汉堡 501 米）会缺这行" % max(no_lm))

print()
print("=" * 68)
print("G. 还债方案（各档位）")
print("=" * 68)
for k in [0, 50, 300, 800, 2000, 10000]:
    try:
        p = m.payoff_plans(k)
        print("  %-6d kcal → %d 个方案：%s" % (k, len(p), (p[0][:44] + "…") if p else "空"))
        if not p:
            warns.append("payoff_plans(%d) 返回空" % k)
    except Exception as e:
        fails.append("payoff_plans(%s) 崩溃：%s" % (k, e))
        print("  💥 %-6d kcal → %s: %s" % (k, type(e).__name__, e))

print()
print("=" * 68)
print("H. 全库遍历渲染（158 条逐一渲染，找个别商品崩）")
print("=" * 68)
crash = []
for n in TABLE:
    try:
        rec, miss = m.build_records([n], TABLE)
        text = m.render(rec)
        if not text or "None" in text or "nan" in text.lower():
            crash.append((n, "渲染产物含 None/nan"))
    except Exception as e:
        crash.append((n, "%s: %s" % (type(e).__name__, e)))
if crash:
    for n, why in crash[:10]:
        print("  💥 %-28s %s" % (n, why))
        fails.append("渲染 %s 崩溃：%s" % (n, why))
else:
    print("  ✅ 全库 %d 条逐一渲染无异常、无 None/nan" % len(TABLE))

print()
print("=" * 68)
print("I. 库外词与畸形查询")
print("=" * 68)
for q in ["螺蛳粉", "🍔", "'; DROP TABLE --", "巨" * 500, "\x00\x01", "<script>alert(1)</script>"]:
    try:
        r = m.resolve_name(q, TABLE)
        print("  ✅ %-30s → %s" % (repr(q)[:28], r))
    except Exception as e:
        fails.append("resolve_name(%r) 崩溃：%s" % (q[:20], e))
        print("  💥 %-30s → %s: %s" % (repr(q)[:28], type(e).__name__, e))

print()
print("=" * 68)
print("J. JSON 输出结构（消费端契约）")
print("=" * 68)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    m.main(["巨无霸", "中薯条", "--json"])
import json
try:
    d = json.loads(buf.getvalue())
    required = ["items", "totalKcal", "rank", "conversion", "payoff"]
    missing_keys = [k for k in required if k not in d]
    if missing_keys:
        fails.append("JSON 缺顶层键：%s" % missing_keys)
        print("  ❌ 缺顶层键：%s" % missing_keys)
    else:
        print("  ✅ 顶层键齐全：%s" % list(d.keys()))
    c = d["conversion"]
    print("  ✅ conversion 键 %d 个" % len(c))
    if "missing" not in d and "unmatched" not in d:
        warns.append("JSON 未暴露 unmatched/missing 字段，调用方无法感知被跳过的词")
        print("  ⚠️  JSON 未暴露 unmatched 字段 —— 调用方不知道哪些词被跳过了")
except Exception as e:
    fails.append("JSON 解析失败：%s" % e)
    print("  💥 JSON 解析失败：%s" % e)

print()
print("=" * 68)
print("结论")
print("=" * 68)
print("崩溃/错误 %d 项，提示 %d 项" % (len(fails), len(warns)))
for f in fails:
    print("  ❌ %s" % f)
for w in warns:
    print("  ⚠️  %s" % w)
sys.exit(1 if fails else 0)

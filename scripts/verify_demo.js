/* 校验 index.html 内嵌的 JS 引擎与 Python 引擎是否逐项一致。
   做法：从 index.html 抠出 <script id="engine"> 块直接执行，跑与
   calorie_engine.py --doctor 相同的基准项。 */
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(
  path.join(__dirname, "..", "index.html"), "utf8");

const m = html.match(/<script id="engine">([\s\S]*?)<\/script>/);
if (!m) { console.error("❌ 抠不出 engine 块"); process.exit(1); }

(0, eval)(m[1]);
const E = globalThis.Engine;

let pass = 0, fail = 0;
function check(name, ok, detail) {
  console.log((ok ? "✅" : "❌") + " " + name.padEnd(34) + " " + detail);
  ok ? pass++ : fail++;
}

const T = E.TABLE;
check("营养库加载", Object.keys(T).length === 158, Object.keys(T).length + " 条商品");

// 别名表目标均存在
const badAlias = Object.keys(E.ALIASES).filter(k => !T[E.ALIASES[k]]);
check("别名表目标均存在", badAlias.length === 0,
  badAlias.length ? "缺失: " + badAlias.join(",") : "共 " + Object.keys(E.ALIASES).length + " 条全部命中");

// 全库自解析唯一（防止串味）
const selfBad = Object.keys(T).filter(n => E.resolveName(n) !== n);
check("库内条目自解析唯一", selfBad.length === 0,
  selfBad.length ? "串味: " + selfBad.slice(0, 5).join(",") : Object.keys(T).length + " 条全部自洽");

// 基准数值（与 Python --doctor 同一组）
const baseline = [["巨无霸", 513], ["双层安格斯厚牛堡", 1003], ["大薯", 379], ["无糖可口可乐中杯", 0]];
baseline.forEach(function (b) {
  const r = E.resolveName(b[0]);
  const got = r ? T[r].k : null;
  check("基准 " + b[0] + " = " + b[1] + " kcal", got === b[1], "实际 " + (got === null ? "解析失败" : got));
});

const total = T["巨无霸"].k + T["中薯条"].k;
check("基准合计 巨无霸+中薯条 = 802", total === 802, "实际 " + total);

// 零热量键集合恒定
const kh = Object.keys(E.convert(800, 60)).sort().join(",");
const kz = Object.keys(E.convert(0, 60)).sort().join(",");
check("零热量返回字段完整", kh === kz, "字段一致（" + Object.keys(E.convert(0, 60)).length + " 个）");

// 别名解析
[["大薯", "大薯条"], ["板烧", "板烧鸡腿堡"], ["零度", "无糖可口可乐中杯"], ["big mac", "巨无霸"]]
  .forEach(function (a) {
    check("别名 " + a[0] + " -> " + a[1], E.resolveName(a[0]) === a[1], "实际 " + E.resolveName(a[0]));
  });

// 层数换算（与 Python 实测值对齐）
const c = E.convert(802, 60);
check("802kcal/60kg 爬楼层数 = 456", Math.round(c["爬楼层数"]) === 456, Math.round(c["爬楼层数"]) + " 层");
check("802kcal/60kg 爬楼分钟 = 91", Math.round(c["爬楼分钟"]) === 91, Math.round(c["爬楼分钟"]) + " 分钟");
// 爬楼高度按「层数 × 3 米」实算：455.6818 × 3 = 1367.05 -> 1367
check("802kcal 爬楼高度 = 1367 米", Math.round(c["爬楼高度米"]) === 1367, Math.round(c["爬楼高度米"]) + " 米");

// 段位
check("段位 802 -> 黄金麦友", E.rankOf(802) === "黄金麦友", E.rankOf(802));
check("段位 294 -> 青铜麦友", E.rankOf(294) === "青铜麦友", E.rankOf(294));

// 地标参照
const lm = E.landmarkNote(1368);
check("地标参照存在", !!lm, lm ? lm.ratio.toFixed(2) + " 个" + lm.name : "无");

// 三个真实场景锚点：与 Python 引擎实测输出逐项对齐
const scenes = [
  { names: ["吉士汉堡", "无糖可口可乐中杯"], kcal: 294, floors: 167 },
  { names: ["巨无霸", "中薯条"], kcal: 802, floors: 456 },
  { names: ["双层安格斯厚牛堡", "大薯条", "麦辣鸡腿汉堡", "无糖可口可乐中杯"], kcal: 1867, floors: 1061 }
];
scenes.forEach(function (s) {
  const r = E.buildRecords(s.names, 60);
  const t = r.records.reduce(function (a, b) { return a + b.kcal; }, 0);
  const cv = E.convert(t, 60);
  check("场景 " + s.names.join("+").slice(0, 14), t === s.kcal && Math.round(cv["爬楼层数"]) === s.floors,
    t + " kcal / " + Math.round(cv["爬楼层数"]) + " 层 / " + E.rankOf(t));
});

console.log("\n" + (fail ? "❌ " + fail + " / " + (pass + fail) + " 项失败" : "✅ 全部 " + pass + " 项通过（JS 引擎与 Python 引擎一致）"));
process.exit(fail ? 1 : 0);

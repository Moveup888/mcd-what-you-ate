# WorkBuddy 开发对话上下文

> 本文件记录 `mcd-what-you-ate` 在 **腾讯 WorkBuddy** 中的开发过程，用于核验本项目符合「麦当劳程序员创意开发大赛」WorkBuddy 联动奖励条件。

## 开发环境

| 项目 | 值 |
|---|---|
| 开发工具 | 腾讯 WorkBuddy（Agent 模式） |
| MCP 接入方式 | WorkBuddy 连接器 → 自定义连接器 → 配置 MCP |
| 接入的 Server | `mcd-mcp`（`https://mcp.mcd.cn`，Streamable HTTP） |
| 工作目录 | `mcd-what-you-ate/` |

## 开发过程实录

### 阶段 1 · 赛事规则核实

在 WorkBuddy 中拉取并交叉核对了活动仓库的 `README.md`、`activityGuidelines.md`、`CONTEST_DECLARATION.md`、`RANKING.md`，以及 `mcd-mcp-server` 的完整 Tool 清单，确认了：

- 报名必备文件共 5 项（其中 `mcp-config.example.json` 只在活动规则里出现，官方 README 的表格并未列出，属易漏项）
- 定榜口径为 2026-10-26 00:00 采集的公开 Star 数
- 内容合规红线：禁止贬低麦当劳品牌、禁止与其他品牌对比、禁止宣扬不健康饮食观念

**该环节结论直接决定了本项目的定位**——从最初设想的"热量警察"改为"热量翻译官"，以保证合规。

### 阶段 2 · MCP 连通性验证

在 WorkBuddy 中直接调用麦当劳 MCP，逐个验证 Tool 可用性：

| 验证的 Tool | 结果 |
|---|---|
| `now-time-info` | ✅ 返回服务端时间 |
| `query-my-account` | ✅ 返回积分账户 |
| `query-my-coupons` | ✅ 返回卡包 10 张券 |
| `available-coupons` | ✅ 返回麦麦省可领券 |
| `campaign-calendar` | ✅ 返回当月活动 |
| `query-nearby-stores` | ✅ 返回深圳科技园 5 家门店 |
| `query-store-coupons` | ✅ 返回门店可用券 |
| `query-meals` | ✅ 返回在售约 130 个 SKU 含价格 |
| `list-nutrition-foods` | ✅ 返回 160 条营养数据 |

### 阶段 3 · 数据缺陷挖掘

在实际调用结果中发现三个关键数据特性，构成本项目的差异化基础：

1. **`nutritionDescription` 字段全库仅 3 条有值**，且「芝士安格斯厚牛堡」（实际 696 kcal）被标注为「能量约鲈鱼1条」，数量级明显不符。
2. **`query-nearby-stores` 返回的经纬度均为 `0.0`**，坐标不可用，只有 `distance` 有效。
3. **菜单存在 `随单购麦金卡优惠`**，必须同时传 `withOrder{membershipCode:"106", specId:"880"}` 才享受优惠价。

### 阶段 4 · 选题与定位

在 WorkBuddy 中对比了排行榜现有同类项目（`mcd-calorie-butler` 93★、`mcd-order-calories` 37★、`mcd-100kcal` 16★ 等），确认热量赛道已拥挤，进而确定差异化方向：

- **不做** "输入热量预算 → 推荐套餐"（已有多个项目在做）
- **做** "输入已吃订单 → 翻译成人话 + 给还债方案"（方向相反）

### 阶段 5 · IP 形象生成

在 WorkBuddy 中生成并迭代 IP 形象：

| 版本 | 结果 |
|---|---|
| v1.0 | 楼梯角度失真、手部与栏杆粘连、配色偏离 → 弃用 |
| v2.0 | 楼梯清晰可数、姿态有动感、红黄主色干净、无文字无商标风险 → 采用 |

### 阶段 6 · 换算引擎开发与验证

在 WorkBuddy 中编写 `scripts/calorie_engine.py`（纯标准库，无第三方依赖），并逐个用例验证：

| 用例 | 结果 |
|---|---|
| `巨无霸 中薯条` | ✅ 802 kcal / 456 层楼 / 黄金麦友 |
| `大薯 板烧 双层安格斯 零度`（别名解析） | ✅ 4 项全部正确匹配 |
| `无糖可口可乐中杯`（零热量边界） | ✅ 修复了 ZeroDivision 崩溃 |
| `螺蛳粉`（库外输入） | ✅ 优雅报错并提示，退出码 2 |
| `--json` | ✅ 结构化输出正常 |
| `--list` | ✅ 列出 158 条去重 SKU |

> 开发中共发现并修复 1 个真实缺陷：零热量输入会因 `convert()` 提前返回而触发 `KeyError`。

### 阶段 7 · 交付物产出

在 WorkBuddy 中生成 5 个报名必备文件、Skill 定义与本文档。其中 `CONTEST_DECLARATION.md` 直接从官方仓库拉取原件（md5 `91a7b32ec28098b609ca3f215cdf7147`），**未作任何修改**。

## WorkBuddy 使用要点

本项目在以下环节**强依赖 WorkBuddy**：

1. **MCP 连接器托管** —— 通过 WorkBuddy 的自定义连接器接入麦当劳 MCP，无需自建 MCP Client
2. **多 Tool 编排** —— 在单次对话中连续调用 6 个 MCP Tool 并交叉比对返回结果
3. **数据缺陷发现** —— 依赖 Agent 对原始 API 返回值的阅读能力，才发现 `nutritionDescription` 仅 3 条有值、经纬度为 0 等隐性问题
4. **代码生成与验证闭环** —— 引擎代码由 WorkBuddy 编写并当场执行验证，发现并修复缺陷
5. **图像生成** —— IP 形象由 WorkBuddy 生成并迭代
6. **文档产出** —— 全部 Markdown 交付物由 WorkBuddy 生成

---

*本文件由 WorkBuddy 开发过程中的对话上下文整理而成。*

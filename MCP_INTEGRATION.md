# MCP 集成说明

本文档说明 `mcd-what-you-ate` 实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。

## 一、使用的 MCP Server

| 项目 | 值 |
|---|---|
| Server 名称 | `mcd-mcp`（麦当劳中国 MCP Server） |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 鉴权方式 | 请求头 `Authorization: Bearer <MCP_TOKEN>` |
| Token 申请 | https://open.mcd.cn/mcp （手机号登录 → 控制台 → 激活） |
| 官方文档 | https://github.com/M-China/mcd-mcp-server |
| 限流 | 600 次请求 / 分钟，超出返回 429 |

本项目**真实调用**麦当劳 MCP 获取餐品营养数据与菜单数据，所有热量数字均来自官方接口返回值，不做估算、不硬编码第三方数据。

## 二、使用的 Tool 清单

| # | Tool | 在本项目中的作用 | 必要性 |
|---|---|---|---|
| 1 | `list-nutrition-foods` | 拉取全量餐品营养成分（能量/蛋白质/脂肪/碳水/钠/钙），是换算引擎的**唯一热量来源** | 核心 |
| 2 | `query-meals` | 拉取指定门店在售菜单与实时价格，用于把用户口语订单对齐到真实 SKU | 核心 |
| 3 | `query-nearby-stores` | 解析用户附近门店，拿到 `storeCode` 供菜单查询使用 | 核心 |
| 4 | `query-store-coupons` | 查该门店可用券，在账单里附带"用券后这一单少欠多少层楼" | 增强 |
| 5 | `now-time-info` | 获取服务端时间，用于判断早餐/正餐时段（影响可用餐品与券） | 增强 |
| 6 | `campaign-calendar` | 查当月活动，用于在账单里提示"今天有 XX 活动，可以直接减层数" | 增强 |

> 本项目**只读**调用麦当劳 MCP，不涉及 `create-order` / `cancel-order` 等写操作，不会代替用户下单。

## 三、调用流程

```
用户输入：我中午吃了巨无霸 + 中薯条
        │
        ├─[1]─ list-nutrition-foods
        │        → 160 条餐品营养数据（全量快照，本地缓存于 data/nutrition_raw.csv）
        │
        ├─[2]─ query-nearby-stores(city, keyword, beType=1, searchType=2)
        │        → storeCode（例：1420762）
        │
        ├─[3]─ query-meals(storeCode, orderType=1, beType=1)
        │        → 在售 SKU 与价格，用于把"巨无霸"对齐到营养库正式名
        │
        ├─[4]─ query-store-coupons(storeCode, orderType=1, beType=1)   ← 可选
        │        → 门店可用券，计算用券后的净热量
        │
        └─[5]─ scripts/calorie_engine.py  ← 本地计算，不再调用 MCP
                 → 爬楼层数 / 跑步分钟 / 深蹲次数 / 米饭碗数 / 段位 / 还债方案
```

### 参数传递规则（易错点）

| 就餐方式 | beType | orderType | beCode |
|---|---|---|---|
| 到店自取 | 1 | 1 | 不传 |
| 得来速 | 5 | 1 | **必传**（来自 `query-nearby-stores`） |
| 麦乐送 | 2 | 2 | **必传**（来自 `delivery-query-stores`） |
| 企业团餐 | 6 | 2 | **必传**（来自 `delivery-query-stores`） |

本项目默认走「到店自取」（`beType=1, orderType=1`），无需 `beCode`，链路最短、最不易出错。

## 四、开发中发现的三个数据特性（已在代码中处理）

### 1. `nutritionDescription` 字段几乎全空

官方营养库 160 条记录中，`nutritionDescription` 有值的**仅 3 条**：

| 餐品 | 官方原文 | 实际热量 | 判断 |
|---|---|---|---|
| 纯悦 | 能量约清水1杯 | 0 kcal | ✅ 合理 |
| 柠檬拉明顿 | 能量约猕猴桃2个 | 121 kcal | ✅ 合理（猕猴桃约 60 kcal/个） |
| 芝士安格斯厚牛堡 | 能量约鲈鱼1条 | **696 kcal** | ❌ 数量级明显不符（鲈鱼约 120 kcal/条） |

**这说明该字段几乎没有被维护，且存在错误。** 本项目因此不依赖该字段，而是自建完整的换算体系，把全部 158 个去重 SKU 都翻译成可读的生活化当量——这正是本项目的价值缺口所在。

### 2. 门店接口不返回可用经纬度

`query-nearby-stores` 返回的 `longitude` / `latitude` 均为 `0.0`，只有 `distance` 有效。

**处理方式**：本项目不做地图渲染与路径规划，只用 `distance` 展示"最近门店距离"，避免依赖不存在的坐标数据。

### 3. 菜单名称与营养库名称口径不一致，且存在复杂定价

- 营养库叫「巨无霸」，菜单里可能叫「巨无霸三件套」「巨无霸四件套」，需按 SKU 区分。
- 菜单存在 `discountType = 随单购麦金卡优惠`，必须同时传 `withOrder{membershipCode:"106", specId:"880"}` 才能享受优惠价，否则按原价计算。

**处理方式**：在 `scripts/calorie_engine.py` 中建立 `ALIASES` 别名表（如 `大薯 → 大薯条`、`零度 → 无糖可口可乐中杯`），并对未识别的输入做显式提示而非静默丢弃。

## 五、业务价值

| 维度 | 说明 |
|---|---|
| 对用户 | 把抽象的热量数字，翻译成"爬多少层楼 / 跑多久"这类能立刻感知的量；并给出可执行的三个运动出口，不停留在制造焦虑 |
| 对开发者 | 演示了如何用麦当劳 MCP 的只读能力（营养 + 菜单 + 券）组合出一个完整可用的消费决策工具 |
| 对生态 | 补全了官方 `nutritionDescription` 字段留下的空白，覆盖 158 个 SKU，且所有数字可复算、可审计 |
| 合规 | 全程只读、不做评判、不与其他品牌对比、输出必带参考免责说明 |

## 六、错误处理

| 错误码 | 含义 | 本项目的处理 |
|---|---|---|
| 401 | Token 无效或过期 | 提示用户重新在 open.mcd.cn/mcp 激活并更换 Token |
| 429 | 触发限流（>600 次/分钟） | 使用本地 `data/nutrition_raw.csv` 缓存兜底，不做高频轮询 |
| 未匹配到餐品 | 用户输入了库外名称 | 显式列出未识别项并建议改用正式名，不静默丢弃 |

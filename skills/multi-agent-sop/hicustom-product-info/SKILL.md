---
version: v1.0
---

# HICUSTOM Product Info Extractor

从 hicustom.com / jit.hicustom.com（指纹科技）商品详情页通过 **API 拦截**提取结构化商品信息。

## 触发条件

用户提供 hicustom.com 商品详情页 URL 时触发：
- "帮我提取这个 hicustom 商品的详情"
- "获取这个商品的信息" + hicustom URL
- "拉取 hicustom 的商品数据"

## 页面架构

| 层面 | 技术 | 说明 |
|------|------|------|
| 登录页 | 服务端渲染 + jQuery | 微信扫码/账号/手机号/QQ 登录 |
| 外层壳 | Vue.js SPA (static.hihumbird.com) | Ant Design 布局 + 导航 |
| 商品内容 | wujie 微前端 iframe | `<iframe name="fnsz-sale">` 嵌套渲染 |
| 数据层 | REST API (apigw.hihumbird.com) | 3 个关键端点（见下方） |

**必须登录才能访问商品详情。**

## 提取字段

| 字段 | 来源 API | 路径 |
|------|---------|------|
| `product_name` | spu-itg | `data.name` |
| `unit_price` | spu-itg | `data.skus[0].sku_price_template.price_level_factors[0].calculate_value` (C级=1件) |
| `estimated_shipping` | spu_freight | `data[0].freight` + `.method_name` + `.country_code` |
| `weight` | spu-itg | `data.skus[0].weight` (g) |
| `color_variants` | spu-itg | `data.attribute_items` type=1 |
| `size_variants` | spu-itg | `data.attribute_items` type=2 |
| `product_details` | spu-itg | `data.extra.spu_features.{material_description, performance, ...}` — 自动剔除：商品编码、底款编码、"默认工艺路线" |
| `package_specs` | product/styles | `data.skus[0].{length, width, height}` (英寸) + `weight`/`net_weight` (g) |
| `images` | spu-itg | `data.images[].file_path` |

### 额外输出
- `price_tiers`: 完整价格阶梯 (C/V1-V5, 1-∞件)
- `blank_code`: 白品编码
- `style_code`: 款式编码
- `factory`: 工厂名称
- `category`: 品类路径
- `delivery_period_hours`: 出货周期

## 三个关键 API 端点

| 端点 | URL 模式 | 返回 |
|------|---------|------|
| SPU 商品 | `apigw.hihumbird.com/spu-itg/uct/v1/spus/{spu_id}` | 名称/价格/变体/详情/图片/工厂 |
| Style 工艺 | `apigw.hihumbird.com/product/uct/v1/styles/{style_id}` | 包装尺寸/净重/毛重 |
| 最低运费 | `apigw.hihumbird.com/spu/v1/spu_freight/lowest_freight` | 运费/物流方式 |

**数据结构**: 响应格式为 `{result_code, msg, data: {...}}`，商品数据在 `data` 直接层级。

## 使用方式

### 🚀 一键同步（推荐）

```bash
# 提取商品信息 → 上传图片 → 写入飞书多维表格
python scripts/sync_to_feishu.py "https://jit.hicustom.com/merchant/.../productDetail?id=xxx"

# 强制重新登录（会话过期时）
python scripts/sync_to_feishu.py "URL" --force-login

# 跳过图片上传
python scripts/sync_to_feishu.py "URL" --no-images

# 强制重新抓取并覆盖（即使已存在且无变化）——用于刷新运费/价格等数据
python scripts/sync_to_feishu.py "URL" --force-update

# 安全预览：只构造字段并打印（含商品基础信息），不写飞书
python scripts/sync_to_feishu.py "URL" --dry-run

# JSON 输出
python scripts/sync_to_feishu.py "URL" --output json
```

**飞书目标表**: `ONy9bZ0oFaaiSEsf4ggcs61enRc` / `tbl75glY29VulRLm`

### 查重与更新机制

同步前自动按「商品ID」字段查重，三种结果：

| 场景 | 行为 | action |
|------|------|--------|
| 商品ID不存在 | 新建记录 | `created` |
| 商品ID存在 + 信息无变化 | 跳过，不做任何操作 | `skipped` |
| 商品ID存在 + 信息有变化 | 更新已有记录（含图片） | `updated` |
| 加 `--force-update` | 无视 diff，强制重新抓取并覆盖全部字段 | `updated` |

比对的字段：商品名称、单价、预估运费、重量、颜色、尺码、包装规格、工厂、出货周期、商品详情、**商品基础信息**。

> ⚠️ **商品基础信息由本采集器一并维护**：`sync_to_feishu.py` 在映射阶段用采集数据直接构造「商品基础信息」字段（模板 `=== PRODUCT IDENTITY ===` / `=== DESIGN INPUTS ===`，与下游 01_Router / aistudio-image-bridge 消费格式一致），**不再依赖独立的 Scraper Agent 环节**。构造来源：商品名称←`product_name`、品类←`category`(category_name)、印花类型←`print_type`、材质说明/适用场景←`商品详情`固定前缀行、颜色←`color_variants`。空字段不输出该行。

> ⚠️ 「跳过」只发生在「已存在且字段完全一致」时，这是正常查重，不是罢工。
> 想刷新已有数据（如复查运费）就加 `--force-update`。

### 仅提取（不写飞书）

```bash
# 首次使用 — 弹出浏览器窗口，完成登录
python scripts/extract_product.py "URL" --headless false

# 后续使用 — 后台无头模式，复用已保存的会话
python scripts/extract_product.py "URL" --headless true

# JSON 输出
python scripts/extract_product.py "URL" --output json

# 调试模式 — 导出 HTML/截图/API 响应
python scripts/extract_product.py "URL" --debug
```

## 命令行参数

### sync_to_feishu.py（一键同步 Bot）

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `url` | 商品详情页 URL | 必填 |
| `--force-login` | 强制重新登录 | false |
| `--no-images` | 跳过图片上传 | false |
| `--force-update` | 无视查重差异，强制覆盖已有记录 | false |
| `--output` | 输出格式 (json/text) | text |
| `--zip` | 预估运费邮编 | 33101 |
| `--timeout` | 页面加载超时(秒) | 60 |
| `--debug` | 导出调试文件 | false |
| `--interactive-freight` | 通过浏览器点击交互试算运费 | false |
| `--dry-run` | 只构造字段并打印预览，不写飞书 | false |

### extract_product.py（仅提取）

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `url` | 商品详情页 URL | 必填 |
| `--zip` | 预估运费邮编 | 33101 |
| `--output` | 输出格式 (json/text/csv) | text |
| `--headless` | 无头模式 (true/false) | 有会话时 true |
| `--force-login` | 强制重新登录 | false |
| `--debug` | 导出页面 HTML/截图 | false |
| `--timeout` | 页面加载超时(秒) | 60 |
| `--download-image` | 下载首张商品图片到当前目录 | false |
| `--interactive-freight` | 通过浏览器点击「更多成本试算」交互试算运费 | false |

## 提取流程

1. 加载 Playwright 浏览器会话（`~/.hicustom_session/state.json`）
2. 导航到商品页 → `page.on("response")` 拦截所有 JSON API
3. 检测登录状态 → 按需弹出窗口等待用户登录
4. 等待 8s 让 wujie iframe + API 请求完成
5. **匹配 3 个 API** → 按精确字段路径提取数据
6. API 兜底：未匹配到时回退 DOM 提取
7. 映射字段 → 上传图片 → 写入飞书

## 反检测配置

Playwright 启动时自动注入反检测参数（`--disable-blink-features=AutomationControlled` 等），绕过滑块验证。

## 变体字段映射规则

始终固定映射：API `type=1 → 颜色`，`type=2 → 尺码`。不做语义判断，与 hicustom 平台自身分类一致。

## 商品详情过滤规则

提取 `product_details` 时自动执行以下整行剔除：

| 规则 | 行为 |
|------|------|
| **商品编码** | 无论内容是什么，一律剔除 |
| **底款编码** | 无论内容是什么，一律剔除 |
| **生产工艺** | 仅当值为「默认工艺路线」时剔除（其他具体工艺名称保留） |
| **价格说明** | 无论内容是什么，一律剔除 |

其余字段（材质说明、商品性能、适用场景、洗涤说明等）100% 原样保留，不做任何修改。

## 运费试算（三种模式）

### 模式 1: API 拦截（首选）
页面加载时自动调用 `spu/v1/spu_freight/lowest_freight`，提取最低运费。无需额外交互。

### 模式 2: 页面级运费展示（新增）
API 未拦截到运费时，自动从商品详情页直接提取已展示的「预估运费」和物流方式。适合新 UI 在页面直接显示运费的场景。

### 模式 3: 浏览器交互试算（兜底）
通过 `--interactive-freight` 启用，模拟人工操作：
1. 点击商品页上的「更多成本试算」链接
2. 在弹出层输入邮编（默认 33101）
3. 点击「试算」按钮
4. 提取运费结果（多物流方式）
5. 自动关闭弹层

**触发条件**:
- 显式传参 `--interactive-freight` 强制使用
- 或 API、页面级运费均失败时自动降级

**多选择器容错**:
- 触发按钮：「更多成本试算」「成本试算」「运费试算」「预估运费」等
- 弹层：ant-modal / el-dialog / [role="dialog"] 等
- 邮编输入：label:has-text("邮编") + input、input[value="33101"]、input[maxlength="5"]、placeholder 含邮编等
- 试算按钮：「试算」「计算」「查询」「估算」等

**运费选择规则**: 按以下规则选取最优运费：
- 🚀 **中国发货**: 在「递四方」或「云途」中选最低价
- ✈️ **国外发货**: 所有渠道中选最低价
- 🔍 **自动检测**: 含"跨境小包"→中国发货；否则→国外发货
- 📮 **默认邮编**: `33101` (Miami, FL)

## 登录方式

| 方式 | 操作 |
|------|------|
| 微信扫码 | 浏览器窗口展示二维码，手机微信扫码 |
| 账号登录 | 点击「账号登录」→ 输入邮箱/手机号 + 密码 |
| 手机号登录 | 点击「手机号登录」→ 输入手机号 + 验证码 |

## 会话管理

- 会话状态: `~/.hicustom_session/state.json`
- 首次或 `--force-login` 时必须用 `--headless false` 弹出窗口
- 登录成功后自动保存，后续可无头复用
- 会话过期时自动提示重新登录

## 批量采集（batch_sync.py）

从分类页 / 推荐页（chooseProduct URL）一次性抓取整批商品并同步飞书。

```bash
# 基本用法（从推荐页/分类页 URL 抓取整批）
python scripts/batch_sync.py "<chooseProduct URL>"

# 跳过图片（仅刷新文字字段，更快）
python scripts/batch_sync.py "<URL>" --no-images

# 强制重新登录（会话过期）
python scripts/batch_sync.py "<URL>" --force-login

# 强制刷新已有记录（无视查重差异，重新抓取并覆盖）
python scripts/batch_sync.py "<URL>" --force-update
```

**流程**：解析 chooseProduct 页 SPU 列表（含 define_id）→ 构造完整商品详情 URL（带 define_id/rel_app_id/currency_id 等必要参数）→ 逐个调用 `sync()` → 汇总 created/updated/skipped/linked_sibling/error。

**注意**：
- URL 必须带 `define_id` / `rel_app_id` / `currency_id`，否则会跳回首页导致抓取失败。
- 每个商品复用与 `sync_to_feishu.py` 完全相同的查重/更新/同款关联逻辑。
- `--force-update` 会对整批已存在记录强制覆盖，用于统一刷新运费/价格等数据。

## USD 定价重算（recompute_usd.py）

汇率相关操作**一律走 Exchange Rates 技能**（XE.com 实时中间价）。脚本可自助调用该技能取 CNY→USD 汇率并重算飞书表的 4 个美元字段。

**定价模型（用户确认 2026-07-09）**：
- 平台佣金 `FEE = 15%`（在售价中扣除，不计入成本）
- 目标利润率 `MARGIN = 35%`（利润 / 售价，销售利润率）
- **售价 = 2 × 成本 是推导结果**：由 `利润 = 售价×(1-FEE) − 成本` 且 `利润/售价 = MARGIN` → `售价 = 1/(1-FEE-MARGIN) × 成本 = 2 × 成本`。改 FEE/MARGIN 会自动重算，勿把 2 当独立参数。
- **尾数规则（用户确认 2026-07-09）**：最终售价必须以 `.49` / `.99` 结尾（心理定价/charm price，美国商品售价习惯）。先算 `2×成本` 目标价，再吸附到**最近的**允许尾数，利润率因此为 ≈35% 近似（小数点后小幅浮动），尾数严格合规。`recompute_usd.py` 中 `ENDINGS` 常量可改（如 `(0.49, 0.59, 0.99)` 三选一）。

```
成本_USD    = (单价CNY + 预估运费CNY) × 汇率
目标售价     = 成本_USD × 2              (对应 35% 利润率)
最终售价_USD = 吸附(目标售价, .49/.99)   (.49 或 .99 之一)
预估利润_USD = 最终售价_USD × 0.85 − 成本_USD
实际利润率   = 预估利润_USD / 最终售价_USD   (≈ 35%, 近似)
```

```bash
# 自动调用 Exchange Rates 技能取实时汇率并重算全部记录
python scripts/recompute_usd.py --fetch-rate

# 仅预览，不写入飞书
python scripts/recompute_usd.py --fetch-rate --dry-run

# 手动指定汇率（如历史汇率复算）
python scripts/recompute_usd.py --rate 0.146838
```

**注意**：汇率技能依赖 `exchangerate-api.com` 降级源（XE 的本地 Browserless 未启动），网络偶发抖动会返回 `Could not fetch` 错误——重试即可，脚本会如实抛出上游错误不静默。涉及货币/汇率换算的步骤都走此技能，不自行写死汇率。

## 依赖

```bash
pip install playwright
playwright install chromium
```

Python 3.9+, playwright >= 1.50

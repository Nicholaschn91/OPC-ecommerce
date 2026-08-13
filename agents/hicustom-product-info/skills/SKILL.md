---
name: hicustom-product-info
description: 从 hicustom.com 商品详情页提取结构化商品信息（product_name, price, weight, variants 等），同步到飞书 Base A。
version: 1.0.0
author: OPC Team
license: MIT
platforms: [windows, macos, linux]
tags: [hicustom, product-extraction, feishu, scraper]
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
- `category`: 品类路径（见下方品类提取规则）
- `delivery_period_hours`: 出货周期

## 品类提取规则（铁律）

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | 页面 API `data.category` | 直接使用，不做修改 |
| 2 | 页面 DOM 品类文本 | 直接使用，不做修改 |
| 3 | 品类映射表 | references/category_mapping.json |

## 脚本用法

### 单商品提取
```bash
python scripts/extract_product.py --url "https://www.hicustom.com/product?id=123456"
```

### 批量同步到飞书
```bash
python scripts/batch_sync_to_feishu.py --input input_urls.txt --config references/config.example.json
```

### 价格计算
```bash
python scripts/pricing_calculator.py --cost 5.0 --margin 0.35 --platform amazon
```

## 依赖

- Python 3.8+
- requests
- lark_oapi (飞书 SDK)
- 已登录的 hicustom.com session cookie

## 配置

参考 `references/config.example.json`，主要配置项：
- `feishu.app_id`: 飞书应用 ID
- `feishu.app_secret`: 飞书应用密钥
- `feishu.base_id`: Base A ID
- `feishu.table_id`: 表格 ID
- `hicustom.session`: 登录 cookie

## 输出字段映射

| 提取字段 | 飞书字段 | 说明 |
|----------|----------|------|
| `product_name` | 商品名称 | |
| `unit_price` | 单价 (1件) | C级价格 |
| `weight` | 重量(g) | |
| `package_specs` | 包装规格 | 长x宽x高 + 重量 |
| `color_variants` | 颜色 | 逗号分隔 |
| `size_variants` | 尺码 | 逗号分隔 |
| `category` | 品类 | 完整路径 |
| `factory` | 工厂 | |
| `delivery_period_hours` | 出货周期 | 小时数 |
| `images` | 图片 | file_token 数组 |

## 注意事项

1. **登录状态**：必须保持有效的 hicustom.com 登录 session
2. **API 限流**：批量提取时加 delay（建议 0.5s）
3. **错误处理**：单个商品失败不中断整体流程
4. **飞书写入**：使用 UPSERT 逻辑，已有记录则更新

## 版本

- v1.0 (2026-08-14) — 从 hicustom-product-info 仓库合并

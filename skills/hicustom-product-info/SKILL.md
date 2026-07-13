# HiCustom Product Info Skill

## 描述
HiCustom 商品数据采集技能 — 文生图、图生图、多图合成、批量生成。支持 agnes-image-2.1-flash 和 agnes-video-v2.0。

## 触发词
- "采集HiCustom"
- "抓取HiCustom" 
- "拉取商品"
- "批量采集"
- "同步商品到飞书"

## 核心能力
- 单商品采集：解析 HiCustom 商品详情页 DOM/API
- 批量采集：分类页批量同步（含 recommend_id）
- 飞书 Base A 写入：12 个核心字段
- 回读校验：幂等防脏录入
- 交互式运费试算：邮编 33101，按钮 `button:has-text("试 算")`

## 目标飞书表
- Base: `ONy9bZ0oFaaiSEsf4ggcs61enRc`
- Table: `tbl75glY29VulRLm`
- App ID: `cli_a951353ba6b8dbcf`

## 写入字段（12 个核心字段）
| # | 字段名 | 来源 | 类型 |
|---|--------|------|------|
| 1 | 商品名称 | API `spu-itg` → `data.name` | 文本 |
| 2 | 单价 | API `spu-itg` → C级 1件价格 | 数字 |
| 3 | 预估运费 | API `spu_freight` → 最低运费 | 文本 |
| 4 | 重量 | API `spu-itg` → `data.skus[0].weight` (g) | 数字 |
| 5 | 颜色 | API `spu-itg` → `attribute_items` type=1 | 文本 |
| 6 | 尺码 | API `spu-itg` → `attribute_items` type=2 | 文本 |
| 7 | 包装规格 | API `product/styles` → 长宽高(英寸)+重量(g) | 文本 |
| 7 | 工厂 | API `spu-itg` → 工厂名称 | 文本 |
| 8 | 品类 | 页面API > DOM > LLM兜底 | 文本 |
| 9 | 出货周期 | API `spu-itg` → `delivery_period_hours` | 文本 |
| 10 | 商品详情 | API `spu-itg` → `extra.spu_features`（剔除商品编码/底款编码/默认工艺路线） | 多行文本 |
| 11 | 图片 | API `spu-itg` → `images[].file_path` → ImgBB上传 | 附件/URL |

## 脚本
```
~/.workbuddy/skills/hicustom-product-info/scripts/
├── sync_to_feishu.py          # 单品同步主脚本
├── batch_sync_to_feishu.py    # 分类页批量同步
├── extract_product.py         # 商品提取核心
├── pricing_calculator.py      # 运费试算
├── recompute_usd.py           # USD 重算
```

## 运费试算规则
- 默认交互式运费试算，邮编 33101
- 按钮：`button:has-text("试 算")`（非 a 链接"查看完整运费试算方案"）
- 中国发货：含"跨境小包" → 递四方/云途最低价
- 国外发货：无"跨境小包" → 本土物流最低价

## 品类提取优先级
1. 页面 API `data.category` 字段 → 直接使用
2. 页面 DOM 品类文本 → 直接使用
3. 以上皆无 → 主控 Agent LLM 分析兜底，标注 `[LLM推断]`

## 预检规则（30分钟门禁）
采集前必须检查 `~/.hicustom_session/state.json` 的修改时间：
- > 30 分钟 → 必须先 `--force-login` 刷新会话
- ≤ 30 分钟 → 可直接执行

## 依赖
```bash
pip install playwright
playwright install chromium
pip install lark-oapi
```
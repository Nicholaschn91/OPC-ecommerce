# Listing to Feishu Sync Skill

## 描述
本地 Listing 包同步到飞书多维表格 Base B 的技能。

## 触发词
- "同步Listing到飞书"
- "上传Listing包"
- "发布Listing到飞书"

## 核心能力
- 读取本地产品包：`D:\listing产品包\已编号图\{sku_code}\`
- 解析文件名 SEO + ALT 文本 → 直接上架
- 飞书 Base B 写入：listing_title、bullet_points、description、search_terms、Etsy_tags、image_url_1~40、alt_text_1~21
- ImgBB 图床上传
- 飞书查重去重

## 目标飞书表
- Base: `RP5ubb66waZnwDsc2MNcchcCnOb`
- Table: `tblLku5v29ExnvtV`

## 写入字段
| 字段 | 类型 | 说明 |
|------|------|------|
| listing_title | 文本 | 标题 |
| bullet_points | 文本 | 五点描述，换行分隔 |
| description | 文本 | HTML 描述 |
| search_terms | 文本 | ST 关键词 |
| Etsy_tags | 文本 | Etsy 标签，逗号分隔 |
| image_url_1~40 | 附件/URL | 主图+垫图 URL |
| alt_text_1~21 | 文本 | ALT 文本 |

## 关键规则
1. **本地 SEO** = 图片文件名 SEO + ALT 文本 → 直接上架
2. Base A / Base B 桥接问题暂时搁置，以后完善
3. **禁止改写原文内容**（强制逐字提取）
3. **写入后必须查重**：飞书 Base B 同 SKU 存在则跳过/更新

## 脚本
```
~/.workbuddy/skills/listing-to-feishu/scripts/
├── sync_listing.py          # 单品同步
├── batch_sync.py            # 批量同步
├── parse_listing_package.py # 产品包解析
├── imgbb_uploader.py        # ImgBB 上传
├── feishu_writer.py         # 飞书写入
└── dedup_checker.py         # 去重检查
```

## 输入路径约定
```
D:\listing产品包\已编号图\{sku_code}\
├── 1.jpg, 2.jpg, ...        # 主图+垫图
├── title.txt                # 标题
├── bullets.txt              # 五点描述
├── description.html         # HTML 描述
├── search_terms.txt         # ST 关键词
├── etsy_tags.txt            # Etsy Tags
└── alt_texts.txt            # ALT 文本
```

## 调用示例
```python
from skills.listing_to_feishu import ListingFeishuSyncer

syncer = ListingFeishuSyncer()
result = syncer.sync_sku("ABC123")
# result = {"success": True, "record_id": "rec_xxx", "fields_written": 45}
```
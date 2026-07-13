# 知识库索引

> 全局知识库索引：Tracks + Visual + Compliance + Keywords 四合一

---

## 1. 赛道文档

| 代号 | 赛道名称 | 文档路径 | 核心品类信号 | 核心动机信号 | 核心情感信号 |
|------|----------|----------|--------------|--------------|--------------|
| **Track A** | Joyful Gifting | `knowledge-base/Track_A_Gifting.md` | 软家居/定制印刷品/纺织周边 | 送礼/纪念/个性化定制 | 情感共鸣强/有明确收礼人/礼物场景长尾词 |
| **Track B** | Memorial & Healing | `knowledge-base/tracks/Track_B_Memorial.md` | 纪念品/骨灰盒/宠物/人物纪念类 | 哀悼/缅怀/情感疗愈 | 情绪基调肃穆/用户处于失去状态 |
| **Track C** | Home Decor & Woodcraft | `knowledge-base/tracks/Track_C_Woodcraft.md` | 实木/竹制装饰品/手工家居摆件 | 家居美化/品味展示/工艺收藏 | 匠人叙事/材质天然感/无强礼赠意图 |
| **Track D** | Outdoor & Protection Gear | `knowledge-base/tracks/Track_D_Outdoor.md` | 户外装备/防护用品/运动配件 | 功能保护/极端环境使用/耐用性 | 硬核/专业/可信赖/无情感叙事 |
| **Track E** | Industrial & Commercial Tools | `knowledge-base/tracks/Track_E_Industrial.md` | 工具/五金/工业设备配件 | B2B采购/专业施工/商业使用 | 冷静理性/参数驱动/无生活场景 |
| **Track F** | Beauty, Personal Care & Food Contact | `knowledge-base/tracks/Track_F_Beauty.md` | 美妆/护肤/食品接触类/个护仪器 | 自我提升/日常护理/健康生活 | 皮肤安全感/成分信任/仪式感 |
| **Track G** | Baby & Kids | `knowledge-base/tracks/Track_G_Baby.md` | 婴童用品/儿童玩具/母婴配件 | 安全保护/亲子互动/发育支持 | 强安全合规要求/马卡龙配色强制 |
| **Track H** | 3C Digital Accessories | `knowledge-base/tracks/Track_H_3C.md` | 数码配件/电子设备周边/充电/存储类 | 设备保护/效率提升/兼容适配 | 冷静科技感/参数对比驱动 |
| **Track I** | Apparel Accessories | `knowledge-base/tracks/Track_I_Apparel.md` | 服装配件/包袋/鞋帽围巾 | 穿搭搭配/时尚表达/季节场景 | OOTD 生活方式/杂志质感 |
| **Track J** | Home Decor & Wall Art | `knowledge-base/tracks/Track_J_HomeDecor.md` | 墙面艺术品/装饰画/挂件 | 空间美化/色彩搭配/艺术收藏 | 色彩还原精度要求高/无礼赠主导 |
| **Track K** | Home Textiles & Soft Goods | `knowledge-base/tracks/Track_K_HomeTextiles.md` | 床品/毛巾/功能性软家居 | 日常使用/功能性购买/无定制/无礼赠意图 | 纯功能驱动/无情感叙事/材质参数主导 |

---

## 2. 视觉工具库

| 文档 | 说明 |
|------|------|
| `references/Agent_SOP/Visual_Tools.json` | 4 模板 + 17 插件 + 48 战术的全量英文描述库 |

---

## 3. 合规与风控

| 文档 | 说明 |
|------|------|
| `docs/risk-levels.md` | 风险词分级标准（一级/二级/三级） |
| `references/risk_kw_export.md` | 64 条三级风险词导出表 |
| `references/Checklists_&_Dict.md` | 禁用极限词替换库 + 核心材质-买家利益点翻译词典 |

---

## 4. 关键词体系

| 文档/工具 | 说明 |
|-----------|------|
| `tools/keyword_tool.py` | 关键词取用 CLI（T1-T5、排序指标、平台过滤） |
| `tools/process_dual.py` | 双源融合引擎（erank + 西柚） |
| `tools/process_dual.py` | 品类词池构建与过滤 |
| `tools/keyword-pipeline/` | 关键词管道全套脚本 |

---

## 5. 视频生成标准

| 文档 | 说明 |
|------|------|
| `knowledge-base/video-templates/video_script_standard.md` | 15秒通用脚本、4分镜、AI强制规范、Agnes集成规范 |

---

## 6. 品牌与分类

| 文档 | 说明 |
|------|------|
| `references/Agent_SOP/Brand_Registry.json` | 品牌主数据：Brand_ID → brand_color_hex + usage_policy + allowed_slots |
| `references/Agent_SOP/Category_Codes_V3.md` | 品类编码 V3 标准 |

---

## 7. 赛道选择决策表

| 文档 | 说明 |
|------|------|
| `references/Agent_SOP/Router_Track_Selector.md` | 品类×动机×情感 三维交叉矩阵 + 边界仲裁规则 |

---

## 8. Agent SOP 源文件镜像

| 文档 | 说明 |
|------|------|
| `references/Agent_SOP/00_Agent_HiCustom_Scraper.md` | 采集 Agent |
| `references/Agent_SOP/01_Agent_Router.md` | 路由 Agent |
| `references/Agent_SOP/02_Agent_SEO.md` | SEO Agent |
| `references/Agent_SOP/03_Agent_Visual.md` | 视觉 Agent |
| `references/Agent_SOP/04_Agent_Ads.md` | 广告 Agent |
| `references/Agent_SOP/05_Agent_Etsy.md` | Etsy Agent |
| `references/Agent_SOP/06_Agent_eBay_Writer.md` | eBay Agent |
| `references/Agent_SOP/07_Agent_Keyword_Processor.md` | 关键词处理 Agent |

---

## 快速导航

- **需要查找赛道规范** → `knowledge-base/tracks/Track_X.md`
- **需要生成视频脚本** → `knowledge-base/video-templates/video_script_standard.md`
- **需要取词/分级** → `tools/keyword_tool.py`
- **需要合规扫描** → `tools/compliance_checker.py`
- **需要品牌色** → `references/Agent_SOP/Brand_Registry.json`
- **需要赛道选择逻辑** → `references/Agent_SOP/Router_Track_Selector.md`
- **需要词库操作** → `tools/keyword-pipeline/`
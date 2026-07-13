# 风险词分级标准

**版本**: 1.0
**适用**: OPC 多 Agent Listing 生成全流程合规扫描
**更新**: 2026-07-13

---

## 分级总览

| 等级 | 代码 | 典型场景 | 处理动作 | 示例关键词 |
|------|------|----------|----------|------------|
| **一级（致命）** | `fatal` | 法律/平台红线 | **CIRCUIT_BREAK** 立即熔断，禁止输出 | FDA违规声称、FTC违规背书、儿童安全违规、IP侵权、VeRO命中、平台生存红线 |
| **二级（高危）** | `high` | 绝对化用语、无资质宣称、平台特定违规 | 标注 ⚠️ + 给出替代词，**需用户确认"替换"**后回写 | 绝对化用语、无资质"医疗级/有机/环保"、平台特定违规（ST重复/超长、Tags重复） |
| **三级（中危）** | `medium` | 主观形容词过多、情感营销过度、隐性对比 | 静默替换 / 标注建议，**不阻塞流程** | 主观形容词过多、情感营销过度、与竞品隐性对比 |

---

## 一级（致命）详细清单

### 法律法规红线
| 类别 | 违规表述 | 替代/处理 | 监管依据 |
|------|----------|-----------|----------|
| **FDA 违规声称** | "cures cancer", "treats diabetes", "FDA approved" (非药品) | 删除/熔断 | FD&C Act |
| **FTC 违规背书** | "doctor recommended #1", "clinically proven" (无证据) | 删除/熔断 | FTC Act Sec 5 |
| **儿童安全** | 小部件无窒息警示、绳索长度超标 | 熔断 | CPSIA / 16 CFR 1500 |
| **加州 65 提案** | 含铅/邻苯等未警示 | 熔断 | Prop 65 |

### 知识产权红线
| 类别 | 违规表述 | 处理 |
|------|----------|------|
| **商标侵权** | 直接使用他人注册商标（非指称性使用） | 熔断 |
| **VeRO 命中** | eBay VeRO 会员投诉品牌词 | 熔断 |
| **版权图片** | 未授权品牌/影视/游戏图片 | 熔断 |

### 平台生存红线
| 平台 | 红线 | 处理 |
|------|------|------|
| **Amazon** | 操纵评价、变体违规、关键词堆砌品牌词 | 熔断 |
| **Etsy** | 非手工/非复古/非造物用品、IP侵权 | 熔断 |
| **eBay** | VeRO、非实物、联系信息外泄 | 熔断 |

---

## 二级（高危）详细清单

### 绝对化/夸大宣传
| 违规词 | 替代建议 | 适用平台 |
|--------|----------|----------|
| best, top, #1, first, perfect, ultimate, absolute | premium, popular, top-rated, preferred, exquisite, well-crafted, reliable | 所有平台 |
| cure, treat, heal, prevent | helps soothe, support, designed to relieve, helps protect | 所有平台 |
| antibacterial, antimicrobial, sanitize, pest-repellent | easy to clean, hygienic, dust-proof | 所有平台 |
| non-toxic, safe, allergy-free | BPA-free, meets safety standards, fresh | 所有平台 |
| eco-friendly, organic, green, chemical-free | sustainably sourced, organically grown | 所有平台 |
| lifetime warranty, satisfaction guaranteed | 12-month quality support, designed to meet high standards | 所有平台 |
| free shipping, best seller | ships from US warehouse, popular choice | Amazon |

### 平台特定高危
| 平台 | 违规类型 | 典型表述 | 处理 |
|------|----------|----------|------|
| **Amazon ST** | 重复、超长、含品牌/ASIN | "best seller", "ASIN B0xxxx" | 替换/需确认 |
| **Amazon 标题** | 超长、促销词、主观形容词 | "Hot Sale 2024 Best Gift" | 替换/需确认 |
| **Etsy Tags** | 重复、超 20 字符、非英语 | "handmade handmade", "mejor regalo" | 替换/需确认 |
| **eBay 标题** | "For [Brand]" 兼容性表述 | "For iPhone 15 Pro Max" | 需确认改为 "Fits iPhone 15 Pro Max" |
| **Etsy 医疗宣称** | "anxiety relief", "cures eczema" | "helps soothe", "designed to support" | 替换/需确认 |

### 无资质宣称
| 宣称类型 | 必需资质 | 无资质处理 |
|----------|----------|------------|
| "Medical Grade" | FDA 510(k) / ISO 13485 | 替换为 "Professional Grade" |
| "Organic" | USDA Organic / GOTS | 替换为 "Organically Grown" |
| "Hypoallergenic" | 临床测试报告 | 替换为 "Gentle on Sensitive Skin" |
| "Flame Retardant" | CA TB117 / NFPA 701 | 替换为 "Meets Flammability Standards" |

---

## 三级（中危）详细清单

| 类别 | 典型表述 | 处理建议 |
|------|----------|----------|
| **主观形容词过多** | "beautiful, stunning, amazing, luxurious, gorgeous" | 静默删除/替换为物理描述 |
| **情感营销过度** | "you'll love", "perfect gift for", "make your life easier" | 保留功能描述，删除情感渲染 |
| **隐性竞品对比** | "better than other brands", "unlike cheap alternatives" | 删除对比，保留自述优势 |
| **模糊规格** | "high quality material", "premium fabric" | 替换为具体参数："300TC cotton", "304 stainless steel" |
| **未验证来源** | "sourced from finest farms", "artisan crafted" | 要求提供供应链证明，否则静默处理 |

---

## 风险词数据库维护

### 来源
1. **risk_keywords.db** (SQLite) — 核心词库，含 `keyword, alternative, level, platform, risk_type, consequence`
2. **平台政策更新** — 定期同步 Amazon/Etsy/eBay 政策变更
3. **人工审核沉淀** — 真实案例反哺

### 更新流程
```
新增风险词 → 标注等级/平台/类型/替代词 → 写入 risk_keywords.db → 重建关键词管道 → 同步 GitHub
```

### 数据库 Schema
```sql
CREATE TABLE risk_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    alternative TEXT,
    level TEXT NOT NULL,          -- 一级（致命）/二级（高危）/三级（中危）
    platform TEXT NOT NULL,       -- amazon/etsy/ebay/all
    risk_type TEXT NOT NULL,      -- 法律/平台/宣传/医疗/敏感/格式/认证
    consequence TEXT,             -- 违规后果
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(keyword, platform)
);
```

---

## 扫描工具

| 工具 | 调用方式 | 输出 |
|------|----------|------|
| `keyword_tool.py --risk-check` | CLI/代码 | 结构化命中列表 |
| `compliance_checker.py` | CLI/代码 | 完整合规报告 |
| Dify 合规智能体 | API (阻塞模式) | 结构化 JSON + 飞书回写 |

---

## 版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-07-13 | 初版：三级分级、平台分离、替代词映射、数据库 |
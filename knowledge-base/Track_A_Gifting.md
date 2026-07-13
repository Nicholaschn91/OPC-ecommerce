# Track A — Joyful Gifting

> **赛道代号**: A
> **赛道名称**: Joyful Gifting
> **版本**: V1.0
> **更新**: 2026-07-13

---

## 1. 赛道定义

| 维度 | 定义 |
|------|------|
| **核心品类** | 软家居 / 定制印刷品 / 纺织周边 |
| **核心动机** | 送礼 / 纪念 / 个性化定制 |
| **核心情感** | 情感共鸣强 / 有明确收礼人 / 礼物场景长尾词 |
| **典型 SPU** | 定制照片毯、刻字首饰盒、照片抱枕 |

---

## 2. 选轨锚点

### 快速排除清单（命中即锁定 Track A）
- SPU 含 "custom photo print / personalized photo / gift for" + 软家居载体 → **直接锁定 Track A**（规则 B4）
- 品类为定制印刷品（全幅印刷毯/抱枕/手提袋等），且无 B2/B3 信号 → **默认 Track A**

### 仲裁规则
- **B1 礼赠意图覆盖软家居**: 品类命中 Track K 且同时存在礼赠购买动机信号 → **强制升轨至 Track A**
- **B4 定制印刷+软家居+无B2/B3**: 品类为定制印刷品，无哀悼/婴儿信号 → **默认 Track A**

---

## 3. 文案风格指令

| 维度 | 要求 |
|------|------|
| **叙事模式** | 情感共鸣优先，功能描述次之 |
| **关键词部署** | T4 词必须放入标题前 40 字符 + 首图视觉词 + 五点第 1 点痛点钩子 |
| **材质翻译** | 必须读取 `Checklists_&_Dict.md`，将【物理特性】翻译为【买家利益】 |
| **视觉调性** | 莫兰迪色系 / 温暖柔光 / 自然景深 / Tier 2 统治级引擎 |

---

## 4. 7-Shot 战术分配表

| 图位 | USP 级别 | 战术编号 | 视觉象限 | 核心任务 | 关键要求 |
|------|----------|----------|----------|----------|----------|
| **Img1** | 无 | T_01 | A-注意 | 纯白底英雄图 | 必须 T_01 + Template_1 |
| **Img2** | S 级 | T_47 | 场景互动 | "Convince the buyer this locks so securely it can be tossed into a bag without a second thought." | 必须含动作化描述 |
| **Img3** | A 级 | T_XX | 场景互动 | 消除 Img2 顾虑的余震 或 Codex倒推 | 承接上级说服逻辑 |
| **Img4** | A 级 | T_XX | 场景互动 | 承接上级图位说服逻辑 | 如 "材质验证" 支撑 "安全承诺" |
| **Img5** | B 级 | T_XX | 场景互动 | 承接上级图位说服逻辑 | 如 "防水场景" 支撑 "耐用承诺" |
| **Img6** | B 级 | T_XX | 混合/平铺 | 承接上级图位说服逻辑 | 减少决策干扰 |
| **Img7** | 复合收尾 | T_XX | Hybrid/Flatlay | 决策降噪 | 展示 280GSM 折叠边缘的厚实感, 手部参照比例 |

---

## 4.1 战术说明

| 战术 | 核心描述 | 适用条件 |
|------|----------|----------|
| T_01 | 纯白底英雄图 | Img1 强制 |
| T_47 | 动作化描述 + 自然光 | S 级 USP 必须锁定 Img2 |
| T_XX | 根据 USP 与象限动态选择 | Track A 策略文档中战术库中选择 |

---

## 5. A+ 模块选择表

| 模块 | 布局 | 图片数 | 比例 | 尺寸 | Content Assignment |
|------|------|--------|------|------|-------------------|
| Premium Large Image | 单张或轮播 | 1-3 | 21:9 | 2928×1200 | FAQ#3 定制流程 |
| Premium Single Image with Text | 单张+文字叠加 | 1 | 4:3 | 1600×1200 | FAQ#1 材质安全 |
| Premium Dual Image with Text | 左右分屏 | 2 | 16:9 | 1300×700 | FAQ#2/FAQ#4 |
| Premium Carousel | 轮播至多 5 张 | 1-5 | 21:9 | 2928×1200 | 定制流程步骤 |
| Premium Hotspot | 单张+交互热点 | 1 | 21:9 | 2928×1200 | 品牌故事 |

> **FAQ 锚定规则**: 每个 A+ 模块必须锚定 FAQ 中的一条高频顾虑，变成 FAQ 的视觉回答。

---

## 6. 绝对禁令

| 编号 | 禁令 | 说明 |
|------|------|------|
| **M1** | **品牌色限制** | Track A 马卡龙色系强制，品牌色仅允许出现在 A+ Hotspot 徽章边框、Mod5/Mod6 文字色或极简线条装饰 |
| **M2** | **饱和度上限** | 饱和度 ≤ 65%，禁用高饱和霓虹色 |
| **M3** | **禁用场景** | 生日派对、婚礼现场、开箱仪式 |
| **M3** | **ECO-FRIENDLY** | 无认证不可使用 |
| **M4** | **变体去具象** | 除 Img6/7 外，单品展示严禁写死具体颜色/尺寸 |

---

## 7. 选轨置信度评分

```yaml
META:
  赛道代号: Track_A
  选轨置信度: HIGH
  选轨依据: "B4规则直接锁定 — custom photo print + fleece blanket + 无B2/B3信号"
  边界风险: "与Track_K存在品类重叠，已由B1规则升轨"
```

---

## 8. 关键词策略偏好

| 层级 | 角色 | 部署区域 |
|------|------|----------|
| **T4** | 利润尖刀 | 标题前 40 字符、首图视觉词、五点第 1 点 |
| **T3** | 长尾引流 | 标题中后段、五点第 2/3 点场景落地 |
| **T2** | 流量基石 | 五点后两点参数背书、A+ 描述核心骨架 |
| **T1** | 高爆低转 | 仅 ST 后半段、描述底部边缘 |
| **T5** | 全文封杀 | 全文及后台绝对封杀 |

---

## 9. 材质深度翻译词典（摘录）

| 中文材质 | 英文翻译（买家利益点） |
|----------|------------------------|
| 法兰绒 | Ultra-soft coral fleece, retains warmth without weight |
| 珊瑚绒 | Premium coral fleece, buttery soft hand feel, anti-pilling |
| 华夫格 | Breathable waffle-knit cotton, quick-dry & moisture-wicking |
| 珊瑚绒 | Plush coral velvet, cloud-like softness against skin |
| 灯芯绒 | Durable corduroy texture, vintage charm meets modern durability |
| 亚麻 | Natural linen, breathable & temperature-regulating |
| 纯棉 | 100% ringspun cotton, pre-shrunk for lasting fit |
| 缎面 | Luxe satin finish, silky smooth drape |
| 丝绒 | Plush velvet pile, rich color depth & tactile luxury |
| 帆布 | Heavy-duty canvas, abrasion-resistant & weather-ready |

---

*本文档为 Track A 专属规范，不可跨赛道引用。如有冲突，以本文档为准。*
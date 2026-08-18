---
name: agnes-studio
description: Agnes 完整图像处理套件 — 双模式（单能力 + 目标流程编排）+ 自带生成引擎（文生图/垫图/视频/ALT）。单能力：抠图/去背景/透明底（S4）、放大/超分/高清修复（S5）、风格迁移/变油画风/皮克斯风/换画风（S6）、宠物拟人/主体重绘/真人转卡通（S7）、换背景/换装/加道具（S8）、提爪印/剪影/元素提取（S9）、加文字/排版/slogan（S10）、套图/一套图/多尺寸（S11）、系列裂变/色way/出一个系列（S12）、生成印花/设计印花（S1）、查侵权/版权检查/能不能上架（S2）、提取印花/成衣印花还原（S3）、印刷检查/300DPI/CMYK/交付检查（S13）。流程触发：做圣诞套系/宠物套系（F6）、全家福油画墙（F7）、情侣互补款（F8）、纪念时间轴（F9）、爆款裂变（F1）、系列套系裂变（F2）、关键词生成商品（F3）、透明底印花提取（F4）、无缝拼接/四方连续（F5）。底层工具：文生图、垫图生图（gen.py）、视频生成（gen_video.py）、ALT 文本生成（alt.py）。即使用户只说"把这张图变个风格"或"查下这张能不能上架"或"帮我生成一张产品图"也应触发。
when_to_use: 用户需要对图片做单一处理（抠图/放大/换风格/重绘/提元素/加文字/查侵权/印前检查）、目标型成套制作（套系/系列裂变/印花提取）或底层生成/视频/ALT 时使用。
version: v1.0
---

# Agnes Studio — 完整图像处理套件（引擎 + 编排层）

**全自包含**：所有引擎、编排、质检、辅助脚本都在本技能内，无外部依赖。  
**双模式**：每个能力可单独点名调用（快进快出，不走动态规划），也可按目标串成流程（DAG 编排）。两种模式共用同一批提示词资产与质检闸门，单能力产出可无缝接进流程继续加工。

## 核心路由（每次请求第一步）

1. 先判定模式（对应 P0 路由器，规则全文见 `references/prompts-l1.md`）：
   - 用户**点名单一能力**（抠图/查侵权/变油画风/提爪印…）→ `mode=single`，直接执行该能力固定管线，**禁止**调用剧本规划；
   - 用户描述**目标型结果**（"做一套""出一个系列""圣诞套系"）→ `mode=flow`，命中预置流程 F1–F9；预置覆盖不了才动态拼装 custom；
   - 用户要求**底层生成/视频/ALT**（"生成这张图""做个视频""给一组图起 ALT"）→ 走引擎层 `scripts/gen.py` / `gen_video.py` / `alt.py`；
   - 一句话串多个能力（"先抠图再变油画风"）→ `mode=flow, target_id=custom`。
2. 需要结构化理解图片时，跑看图理解器：
   `python scripts/mllm_task.py --task p1_understand --image 来图.jpg [--capability S6]`
3. 单能力产出命名 `<能力ID>_<时间戳>.png` + 同名 `.json` 元数据，供后续流程复用。

## 引擎层（底层工具，2026-08-17 合并 agnes-image 入内）

直接调用即可，无需编排层流程。详细 API 与端点 failover 见 `references/api-notes.md`。

### 文生图 / 垫图生图（gen.py）— 主力模型 `agnes-image-2.1-flash`

```bash
# 文生图
python scripts/gen.py --prompt "a cozy living room with warm sunlight" --output room.png

# 垫图（核心）
python scripts/gen.py --prompt "Same blanket on a wooden table, warm afternoon sunlight" \
  --image blanket.jpg --output blanket_scene.png

# 多张参考图
python scripts/gen.py --prompt "Combine into a cohesive scene" \
  --image product.png --image background.png --output combined.png

# 批量 + 预设提示词
python scripts/gen.py --batch prompts.txt --image ref.png --output batch.png
python scripts/gen.py --preset shaped-mousepad --image product.jpg --output mousepad.png
python scripts/gen.py --list-presets                # 列所有预设
python scripts/gen.py --usage                       # 查今日用量
```

**预设提示词**（含引流预设）：`lineart`/`shaped-mousepad`/`ad-reveal`/`ad-gift`/`ad-ugc`/`ad-craft`/`ad-engrave`。引流预设搭配 `--image` 垫产品主图效果更佳；尺寸按投放渠道选 `--size`（社交广告 `1536x2048` 4:5，TikTok/Reels `2048x2048` 或直接出 9:16 竖屏视频）。完整引流 SOP 见 `external-traffic` 技能。

### 视频生成（gen_video.py）— 模型 `agnes-video-v2.0`

异步任务流：创建任务 → 轮询结果（默认 600s / 5s）→ 下载或仅存 URL。

> **输入图片**：图生视频 / 关键帧的 `--image` 接受三种形式——①本地图片路径（脚本自动读图转 base64 内联，无需图床）；②公网 URL；③`data:` URI。

```bash
# 文生视频
python scripts/gen_video.py --prompt "a cozy mug steaming on a wooden table" --download

# 图生视频
python scripts/gen_video.py --prompt "slow zoom in, gentle breeze" \
  --image https://.../product.png --download

# 关键帧动画
python scripts/gen_video.py --prompt "smooth morph between scenes" \
  --keyframes https://.../k1.png --keyframes https://.../k2.png --download

python scripts/gen_video.py --usage
```

参数速查：`--duration 3|5|10|18`（帧数 8n+1，≤441）、`--resolution 480p|720p|1080p|16:9|9:16|1:1|4:3|3:4|WxH`、`--negative-prompt`、`--seed`、`--inference-steps`、`--max-wait 600`、`--poll-interval 5`。

### ALT 文本生成（alt.py）— 多模态 base64 内联

为电商产品图生成英文 ALT 文本（≤125 字符），无外部图床依赖。

```bash
python scripts/alt.py -i product.png                          # 默认 768px
python scripts/alt.py -i product.png --size 512               # 简单纯色
python scripts/alt.py -i product.png --size 1024              # 极致细节
python scripts/alt.py -i product.png -o alt.txt               # 输出到文件
python scripts/alt.py -i product.png --name "金毛异形暖手抱枕" -o alt.txt   # 带品名
```

**尺寸选择速查（白底产品图）**：512px ~620 token（简单纯色）；**768px ~940 token（推荐默认）**；1024px ~1390 token（边际递减）。`**--name**` 是图生图语义锚点关键，白底图只留产品轮廓、丢了"这是什么"的形态上下文，模型可能误判类型（实测曾把暖手抱枕认成 face mask），用 `--name` 锚定品名。

### 飞书辅助工具

```bash
# 飞书 token 辅助（独立小工具，缓存 token 到 .feishu_token.json）
python scripts/feishu_api.py
```

### 引擎铁律（三铁律，2026-08-17 合并后继承）

1. **铁律1 — 控制并发**：默认**串行执行**。`--concurrency 1|2|3` 临时开启N并发，但不超过3。
2. **铁律2 — 批量延时**：仅在 `--batch` 下生效，每个请求间休眠 2~3s（**已统一为固定值，不再按分辨率区分**）。
3. **铁律3 — 429 重试**：遇 `429 Too Many Requests` 自动暂停 **60 秒** 后重试，最多 3 次。

### 尺寸与速率限制

| 分辨率档位 | 示例尺寸 | RPM限制 | 建议延迟 |
|-----------|---------|---------|---------|
| 1K | 1024x1024, 1024x768, 768x1024 | 20 | 2-3s |
| 2K | 2048x2048, 2048x1536, 1536x2048 | 10 | 2-3s |
| 3K/4K | 3072x3072, 4096x4096 | 1 | 2-3s |

脚本内置保护：日限额检查（`.agnes_usage.json` / `.agnes_video_usage.json`）、RPM 安全、429 自动重试、用量记录。

### ⚠️ 视频缺口（待补）

`gen_video.py` **仅 `.com` 端点**，未做 `.cn` failover（与 `gen.py` / `alt.py` 双端点不一致）。影响比图像更严重：图像可 failover 到 `.cn`，而视频**无任何兜底**——关代理/境内直连时 `.com` 既认证不过也够不到 Google 图床，视频功能直接整体不可用。todo：补 `.cn` 一致化（高优先级）。

## 能力目录（S1–S13，均可单独调用）

| ID | 能力 | 触发词 | 执行入口 |
|---|---|---|---|
| S1 | 印花设计（从0生成） | 生成印花、设计一款印花、做图案 | gen.py 文生图 + 可选 text_layout |
| S2 | 侵权检测 | 查侵权、版权检查、能不能上架、风险自查 | `mllm_task.py --task p12_compliance` |
| S3 | 印花提取 | 提取印花、成衣印花还原、把图案扒下来 | gen.py 垫图两步（展开+去纹理）|
| S4 | 抠图 | 抠图、去背景、透明底 | gen.py 键色垫图 + `keycut.py` |
| S5 | 放大 | 放大、超分、高清修复、upscale | gen.py 垫图超分 |
| S6 | 风格迁移 | 变油画风、皮克斯风、换画风、风格化 | gen.py 垫图（P6+P7+P8 填槽）|
| S7 | 主体保留重绘 | 宠物拟人、真人转卡通、给宠物穿衣服 | gen.py 多图垫图（P10 模板）|
| S8 | 场景/服装替换 | 换背景、换装、加圣诞帽 | gen.py 垫图局部替换 |
| S9 | 元素提取 | 提爪印、要剪影、手写字提取 | `element_extract.py`（吃 S4 透明底）|
| S10 | 文字排版 | 加文字、排版、加slogan、写名字 | `text_layout.py` |
| S11 | 套图生成 | 套图、一套图、多尺寸、主图详情图 | gen.py 批量 + P4 双阈值 |
| S12 | 系列裂变 | 系列裂变、色way、出一个系列 | DNA 解析 + 槽位替换 + 闸门 |
| S13 | 交付检查 | 印刷检查、300DPI、CMYK、能不能印 | `delivery_check.py` |

每个能力的输入/输出/固定管线/降级方案全文：`references/capabilities.md`。执行任何能力前先读对应章节。

## 流程目录（F1–F9，目标型请求才启用）

| ID | 流程 | 触发示例 | 编排（能力序列） |
|---|---|---|---|
| F1 | 爆款商品裂变 | 把这个爆款裂变几个版本 | S4→S2→S7/S6 多维裂变→S11→S13 |
| F2 | 系列套系裂变 | 按这张图出一整个系列 | S12→S11→S13 |
| F3 | 关键词生成商品 | 生成一款花卉印花 | S1→S2→S10→S13 |
| F4 | 透明底印花提取 | 把T恤印花提取出来 | S3→S4→S5→S13 |
| F5 | 无缝拼接印花 | 做成四方连续 | S1/S3→平铺校验→拼接→S13 |
| F6 | 宠物圣诞套系 | 把我家狗做成圣诞套系 | S2→S4→S7→S9→S10→S11→闸门→S13 |
| F7 | 全家福油画墙 | 全家福做成油画挂墙 | S2→多人分割→S6→S11→S10→S13 |
| F8 | 情侣互补款 | 情侣装一对 | S2→双人分割→镜像构图→互补色板→S10→S13 |
| F9 | 纪念时间轴 | 把照片做成时间轴 | EXIF 排序→S10→S13 |

通用规则与逐流程要点：`references/playbooks.md`。

## 硬约束（违反即返工）

1. **禁止本地 ML 抠图**：rembg/BRIA/u2net 等本地分割模型历史实测边缘不达标，一律不用。抠图走 S4（云端键色生成 + `keycut.py` 确定性转 alpha）；元素提取消费 S4 产出的 alpha。
2. **文字分层铁律**：任何要出现在成品上的文字，必须由 `text_layout.py` 渲染叠加，严禁写进生成 prompt。
3. **合规闸门前置**：含生成/上架用途的流程，`copyright_risk` 任一为 true 时必须先过 S2 再生成；S2 单独调用是纯检测，秒级返回。
4. **身份保留**：有人/宠主体的生成必须带 P8 身份保留短语；宠物参考图 <2 张先引导补传，不静默降质。
5. **质检按范围裁剪**：P4 只查当前能力相关项（映射表见 `references/prompts-l1.md`）；重试上限 2 次，超过 escalate 给用户。
6. **限流铁律**（引擎三铁律）：默认串行、批量间隔 2–3s、429 暂停 60s、日限额 4000（视频独立计）、3K/4K 档 RPM=1。

## API 细节（端点 Failover）

图像生成（`gen.py`）与 ALT（`alt.py`）已内置 **Endpoint Failover**：

- **.cn**：`https://api.agnes-ai.cn/v1`
  - 图像 `POST /v1/images/generations` 模型 `agnes-image-2.1-flash`
  - ALT `POST /v1/chat/completions` 模型 `agnes-2.5-flash`
  - ⚠️ 图像结果 URL 落 `storage.googleapis.com`（Google，国内无 VPN 被墙）→ 脚本对 `.cn` **强制 `b64_json` 内联**
- **.com**：`https://apihub.agnes-ai.com/v1`
  - 图像模型 `agnes-image-2.1-flash`；ALT 模型 `agnes-2.0-flash`
  - 结果 URL 在 `platform-outputs.agnes-ai.space`，故 `.com` 用 `url` 输出
- **顺序覆盖**：`AGNES_BASE_URL`（主）/ `AGNES_FALLBACK_URL`（备）环境变量
- **双令牌按域**：`.com` 用 `AGNES_API_KEY`，`.cn` 用 `AGNES_API_KEY_CN`（未配置回退主 key）。**注意**：两域凭据是用户两种代理环境各自的令牌，**并非同一把 key 两域通用**——failover 必须按域名用各自 key，否则兜底端点必 401（2026-08-17 实测：非代理状态下 `.cn` 用 `.com` 的 key 直接 401，两端点同时死，failover 形同虚设）。
- **垫图**：`extra_body.image` 数组（`string[]`），支持公网 URL 与 data URI；图生图**无需** `tags:["img2img"]`
- **response_format 铁律**：必须放 `extra_body.response_format`（严禁顶层）
- **尺寸语法**：`.cn` 新档位 `size:"1K"|"2K"|"3K"|"4K"` + `ratio:"1:1"|...`，仍兼容旧 `1024x1024`；Pinterest 2:3 推荐 `size:"1K" ratio:"2:3"`（832×1248）

详细 endpoint 实测快照（2026-07-28 / 08-16 网络状态）与 key 配置：`references/api-notes.md`。

## 引擎对接（自包含）

- 生成/垫图/视频：`scripts/gen.py` / `scripts/gen_video.py`（自身）
- 多模态理解（P0/P1/P4/P5/P12/P15）：`scripts/mllm_task.py`
- 确定性后处理：`scripts/keycut.py` / `scripts/element_extract.py` / `scripts/text_layout.py` / `scripts/delivery_check.py`
- 资源目录：`assets/`（含 `doll-blank.png` / `head-pillow.jpg` 样例）
- API Key：读 `~/.workbuddy/skills/agnes-studio/.env` 中 `AGNES_API_KEY`

## 执行自检

每次任务收尾时确认：

- [ ] 模式判定正确（单能力没有走动态规划；目标型请求没有拆成零散单能力；底层生成/视频/ALT 走引擎层）
- [ ] 含生成的请求已过合规判断（P1 copyright_risk 或 S2）
- [ ] 涉及主体的生成带了 P8 身份保留短语
- [ ] 文字全部走 text_layout，未混入 prompt
- [ ] 产出经过对应范围的 P4 质检，verdict 与重试次数已记录
- [ ] 实物交付类已过 S13 且 verdict=pass
- [ ] 产出路径与元数据已告知用户，并给出可接续的下一步建议

## 已知局限

- 当前引擎无独立背景移除端点，S4 依赖"键色生成"质量；主体与键色相近时需换键色重跑。
- S3 印花提取为垫图兜底方案，效果上限低于专用配对数据训练的提取模型。
- text_layout 输出位图（矢量为后续版本）；默认字体仅限打样，商用必须换授权字体。
- P11 双阈值（τ1=0.15、τ2=0.35）与 P4 通过线（70 分）均为占位值，需真实样本校准。
- `gen_video.py` 端点缺口：仅 `.com`，未做 `.cn` failover（待补，见缺口 B）。
- 端点可用性受网络环境影响（**2026-08-17 实测 + 勘误**：两个端点凭据均有效，401 是"当前代理状态与该端点预期环境不匹配"而非令牌失效——代理开着时 `.com` 通、`.cn` 401；关代理则相反。failover 会自动选中当前能认证的那个端点，无需手动判断"哪个可用"）。
- **2026-08-17 修复**：`gen.py`/`alt.py` 原默认 `.cn` 主用且 401 时直接退出（不 failover）——已改为默认 `.com` 主用，且 401/403 与网络/5xx 一样触发 failover（按域名用各自令牌）。**同日再修双令牌**：failover 原本"一把 key 两域通用"，与用户"两把令牌对应两种代理环境"的现实不符——改为 `.com` 用 `AGNES_API_KEY`、`.cn` 用 `AGNES_API_KEY_CN`，未配置回退主 key。
- **文档/代码不一致（缺口 A）**：本文件声称 `gen.py` 支持 `size:"1K" + ratio:"2:3"` 档位语法，但 CLI 的 `--size` 仅接受显式 `WxH`（多档位以 1K/2K/3K/4K 显式尺寸覆盖）；`--ratio` 参数未实现。

## 功能计数（自检）

- 引擎层：文生图/垫图/生成/批量/预设/用量/多图/多档位(WxH)/Failover = 13；ALT/尺寸选择/--name/Failover = 4；视频/图生视频/关键帧/时长/分辨率/参数 = 6；辅助工具 = 2 → **引擎 25 个**（size+ratio 档位语法文档声称但 CLI 未暴露）
- 编排层：S1–S13 单能力 = 13；F1–F9 流程 = 9 → **编排 22 个**
- **合计 47 个功能**（含 1 个文档声称但 CLI 未实现的 size/ratio 档位语法）。
- **实测进度（2026-08-17 晚，诚实更新）**：首轮实跑约 **24–26 条**能力路径（引擎 gen 全矩阵/alt/base64/视频/确定性脚本 + 编排 S1/S2/S4/S9/S10/S13 + F3）；**待补测**：S3/S5/S6/S7/S8/S11/S12（7 项）+ F1/F2/F4/F5/F6/F7/F8/F9（8 项）。⚠️ 原"其余 46 项均已逐项实测通过"为**误述**，已纠正——此前是把"底层脚本通"推到"其上能力全过"，并未逐条执行。

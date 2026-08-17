# 能力目录 S1–S13（单独使用菜单）

> 每个能力都是对外的产品单元，可单独调用：直接执行其固定内部管线，**不经过 P2 剧本规划**，快进快出。
> 单独调用的产出同样是标准 Asset（文件 + 元数据 JSON），可无缝接进任何流程。

## 触发词总表

| ID | 能力 | 触发词（用户可能说的话） |
|---|---|---|
| S1 | 印花设计（从0生成） | 生成印花、设计一款印花、从0设计、出一款花卉印花、做图案、设计图案 |
| S2 | 侵权检测 | 查侵权、侵权检测、版权检查、能不能上架、有没有侵权、风险自查、扫一下这张图 |
| S3 | 印花提取 | 提取印花、把这件衣服的印花提取出来、成衣印花还原、把图案扒下来、提取平面稿 |
| S4 | 抠图 | 抠图、抠出来、去背景、透明底、把主体抠出来、cutout、remove background |
| S5 | 放大 | 放大、高清修复、超分、提高分辨率、图太糊了、upscale |
| S6 | 风格迁移 | 变油画风、皮克斯风、换画风、风格化、变成水彩、像素风、换个风格 |
| S7 | 主体保留重绘 | 宠物拟人、把狗做成圣诞角色、卡通化、真人转卡通、给宠物穿衣服 |
| S8 | 场景/服装替换 | 换背景、换场景、换装、加圣诞帽、换个环境、换衣服 |
| S9 | 元素提取 | 提爪印、要个剪影、轮廓剪影、提取元素、手写字提取、要这个爪印图案 |
| S10 | 文字排版 | 加文字、排版、加slogan、写上名字、配文案、加日期、做个文字版 |
| S11 | 套图生成 | 套图、一套图、多角度、多尺寸、主图详情图一套、出套装 |
| S12 | 系列裂变 | 系列裂变、出一个系列、色way、换色、裂变几款、变体、系列款 |
| S13 | 交付检查 | 印刷检查、交付检查、300DPI、CMYK、能不能印、印前检查、出血 |

## 逐能力规格

### S1 印花设计（从0生成）

- **输入**：文字意图（± 参考图）
- **输出**：印花稿 PNG + 元数据 JSON
- **固定管线**：
  1. （可选）P5 文案生成器产出 slogan 候选，用户确认；
  2. agent 按 P3 规则填 P6 元模板（无主体时省略 identity_lock_phrase；印花用 seamless/tileable composition）；
  3. `scripts/gen.py --prompt "<填好的prompt>" --size 2048x2048 --output 印花稿.png`；
  4. 有文字需求时：`scripts/text_layout.py` 渲染文字层后叠加。
- **铁律**：文字永不进生成 prompt（分层铁律）。
- **降级**：生成结果含多余文字伪影 → 在 prompt 末尾追加 avoid 语句重试一次；仍失败 → 交用户人工挑选或改 prompt。

### S2 侵权检测（纯检测）

- **输入**：任意图（支持批量：逐张调用）
- **输出**：风险报告 JSON（不生成任何图片，秒级返回）
- **固定管线**：`python scripts/mllm_task.py --task p12_compliance --image 待检图.jpg`
- **判定后动作**：pass → 放行；need_declaration → 向用户展示声明并要求确认；block → 终止并提示更换图片。
- **降级**：多模态服务不可用 → 明确告知"合规检测暂不可用，请勿用于上架决策"，禁止静默放行。

### S3 印花提取

- **输入**：成衣/商品图（印花带布料褶皱与纹理）
- **输出**：平面印花稿 PNG
- **固定管线**：
  1. P1 看图理解器定位印花区域（输出 position_hint）；
  2. agent 构造"展开平面化"指令，走 gen.py 垫图：prompt 模板见下；
  3. 再走一次"去布料纹理"垫图精修；
  4. P4 质检：与原图印花内容逐项比对（图案元素、颜色、文字）。
- **prompt 模板（展开平面化）**：`Extract the printed graphic from this garment into a flat 2D print design: unfold all fabric wrinkles, remove fabric texture and garment shape, correct perspective, keep every pattern element, color and text exactly as printed, pure white background, flat vector-like result, no shadows`
- **命门提示**：效果上限取决于垫图模型能力；有"成品图↔平面稿"配对数据训练专用模型是后续升级路径，当前为兜底方案。
- **降级**：两次垫图后仍有明显褶皱残留 → 告知用户当前为兜底效果，建议提供更平整的拍摄图。

### S4 抠图（云端生成 + 键色法）

- **输入**：任意图
- **输出**：透明底 PNG（保留原始分辨率）
- **固定管线**：
  1. gen.py 垫图，prompt 用键色模板（见下），输出 1K/2K 结果；
  2. `python scripts/keycut.py --image 键色结果.png --output 透明底.png`（--key 默认 auto：从边缘环带自动检测键色，确定性颜色阈值转 alpha，无任何本地 ML 分割模型；实测 agnes 输出约 RGB(70,183,27) 而非纯绿，auto 可正确命中）；
  3. P4 质检（check_scope=抠图：边缘 halo/缺角、主体完整性）。
- **键色 prompt 模板**：`Place the main subject of this image onto a solid pure chroma-key green background (hex #00FF00), the background must be completely flat, evenly lit, uniform green with no gradient, shadow or vignette; keep the subject exactly unchanged with sharp clean edges; do not add any green tint, rim light or reflection on the subject`
- **硬约束**：**禁止使用本地 rembg/BRIA/u2net 等抠图模型**（历史实测边缘质量不达标）。
- **降级**：键色溢出（主体边缘泛绿）→ 调大 --tolerance 重跑 keycut；主体与绿色相近（绿植等）→ 键色改 #FF00FF 重跑生成；P4 两次不过 → escalate_human。
- **参数基线**：--tolerance 默认 90（欧氏距离），--feather 默认 2px。

### S5 放大

- **输入**：低清图
- **输出**：高清 PNG
- **固定管线**：gen.py 垫图超分，prompt：`Upscale this image to higher resolution: enhance fine details and sharpness, keep all content, colors and composition exactly unchanged, no new elements, no style change`；--size 按目标档位选 2048x2048 / 4096x4096（4K 档 RPM=1，谨慎使用）。
- **降级**：4K 档频繁 429 → 退到 2K 档两次迭代。

### S6 风格迁移

- **输入**：图 + style_id（P7 风格词库）
- **输出**：风格化图 PNG
- **固定管线**：
  1. P1 精简看图（只取 subjects + image_quality）；
  2. agent 填 P6 元模板：style_token 从 P7 整段取用；有人/宠主体时 identity_lock_phrase 从 P8 取；
  3. gen.py 垫图生成；
  4. P4 质检（check_scope=style_match；有主体时加 identity）。
- **降级**：identity_score 不达标 → 加强 P8 短语措辞重试一次；仍不过 → escalate_human。

### S7 主体保留重绘

- **输入**：图（± 参考图，宠物建议 ≥2 张）
- **输出**：重绘图 PNG
- **固定管线**：按 P10 模板（宠物拟人等）或 P6 元模板；参考图全部作为 gen.py --image 传入（原图第一张）；P4 质检（identity + defects）。
- **参考图不足**：宠物主体参考图 <2 张时，先引导用户补传 1–2 张，不静默降质。
- **降级**：两次重绘 identity 不过 → escalate_human，附上 P4 的 retry_advice。

### S8 场景/服装替换

- **输入**：图 + 替换意图
- **输出**：合成图 PNG
- **固定管线**：gen.py 垫图，prompt 明确"只替换 X，主体保持不变"（P8 短语必带）；P4 质检（identity + defects + 替换是否生效）。
- **降级**：主体被连带改动 → prompt 中追加 "the subject itself must remain pixel-faithful" 重试。

### S9 元素提取

- **输入**：透明底 PNG（通常来自 S4 产出）+ 元素类型
- **输出**：元素 PNG（透明底）+ 黑白预览
- **固定管线**：`python scripts/element_extract.py --image 透明底.png --type silhouette|paw_print|handwriting`（纯 alpha/颜色运算，无 ML 分割）
- **硬约束**：禁止本地 ML 抠图；无透明底输入时先走 S4。
- **降级**：paw_print 聚类失败（肉垫与主体颜色接近）→ 请用户确认区域或改用 silhouette。

### S10 文字排版

- **输入**：文字内容 + 位置/字体偏好（± 底图）
- **输出**：成品 PNG（或透明底文字层 PNG）
- **固定管线**：
  1. （可选）P5 生成文案候选，用户确认逐字稿；
  2. `python scripts/text_layout.py --spec spec.json --base 底图.png --output 成品.png`（spec 结构见 P9）；
  3. P4 逐字比对（错一字即重渲）。
- **字体约束**：默认脚本内置字体仅限打样；商用交付必须换有授权字体（spec 中 font 指向字体文件）。

### S11 套图生成

- **输入**：主体图 + style_id + 套系规格（几张、什么构图/尺寸）
- **输出**：多张套图 PNG
- **固定管线**：按 P11 约束包逐张走 gen.py（共用 style_token 与参考图，构图槽位按子图角色变化）；全部完成后 P4 双阈值一致性校验；任一不满足**整组重跑**。
- **降级**：整组重跑两次仍不过 → 缩小套图张数或降 style 强度，escalate_human 说明。

### S12 系列裂变

- **输入**：种子款/图
- **输出**：系列多款（图 + DNA 元数据 JSON）
- **固定管线**：
  1. DNA 解析：P1 看图 + agent 提炼布局骨架/风格词/色板/主体槽位/文案句法（写入 dna.json）；
  2. 槽位替换：按用户指定的裂变维度（色way/风格/构图/主体）逐款填 P6 元模板，走 gen.py；
  3. 双阈值闸门：P4 逐款 + 整组校验（P11）；
  4. 重试闭环：不达标款按 retry_advice 重跑，上限 2 次。
- **降级**：系列感不足 → 收紧 style_token 与 lighting 为逐字相同的固定串重跑整组。

### S13 交付检查

- **输入**：成品文件（± 目标印刷尺寸）
- **输出**：检查报告 JSON（不生成任何图片）
- **固定管线**：`python scripts/delivery_check.py --input 成品.png [--target-width-mm 300] [--cmyk] [--text-safety-mm 5]`
- **判定后动作**：pass → 放行；fix_and_recheck → 指明修复能力（分辨率不足→S5，文字越界→S10 重排，色彩模式→转换工具）。

## 单能力模式的通用约定

1. 产出文件命名：`<能力ID>_<时间戳>_<序号>.png`，元数据 JSON 同名 `.json`。
2. 每次单能力调用结束，向用户报告：产出路径 + 质检结论（如有）+ 可接续的下一步建议（如"要不要把它接进圣诞套系流程？"）。
3. 单能力产出必须能被后续流程直接引用：元数据 JSON 记录 subject_type、style_token、参考图路径，供 P2 规则 7（复用 Asset）使用。

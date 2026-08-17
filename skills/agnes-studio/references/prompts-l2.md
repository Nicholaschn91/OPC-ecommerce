# L2 原子模板与词库（P6–P15）

> 本文件是被 L1 查表引用的资产。改动走版本管理；风格词库新增条目必须先过验证规则（P7 末尾）。

## P6 元模板（图像生成）

所有生成类步骤共用的主模板。agent 按 P3 规则填槽后交给 `scripts/gen.py` 执行。

```text
正向元模板：
{subject_description}, {style_token}, {identity_lock_phrase},
{scene_or_props}, {lighting}, {composition},
high quality, sharp details, print-ready

槽位说明：
- subject_description  主体描述，来自 Asset 元数据（英文）
- style_token          从风格词库整段取用（见 P7）
- identity_lock_phrase 从身份保留短语表取用（见 P8）；无主体的纯风格化可省略
- scene_or_props       场景/服装/道具，可为空
- lighting             光照，默认 soft studio lighting
- composition          构图，默认 centered composition；印花用 seamless/repeat 时另行指定

通用负向模板（作为 agent 自检清单；当前 gen.py 单 prompt 接口下，
将负向意图合并为 "avoid ..." 尾句写入 prompt 末尾）：
lowres, blurry, extra limbs, deformed face, distorted anatomy,
watermark, text, logo, signature, jpeg artifacts
```

**填充示例**（柯基 + 圣诞 + 皮克斯风）：

```text
the corgi from the reference image as a santa character, wearing a red santa hat with white fur trim,
3d pixar style render, soft subsurface scattering, big expressive eyes, smooth stylized shapes,
preserve exact fur pattern, coat color and face markings, same pet,
festive red and green background with soft bokeh, soft studio lighting, centered composition,
high quality, sharp details, print-ready
```

## P7 风格词库表

一张表，不是 prompt。按 style_id 整段取用。先保持小，跑出数据后再扩。

| style_id | 中文名 | style_token（英文，整段使用） | 适合主体 | 建议强度 |
|---|---|---|---|---|
| oil_painting | 油画 | oil painting, thick brushstrokes, impasto texture, canvas grain | 人像/宠物/全家福 | 0.6–0.8 |
| pixar_3d | 皮克斯3D | 3d pixar style render, soft subsurface scattering, big expressive eyes, smooth stylized shapes | 人像/宠物 | 0.7–0.9 |
| watercolor | 水彩 | delicate watercolor, soft color bleed, paper texture, light washes | 人像/宠物/花卉 | 0.5–0.7 |
| pixel_art | 像素 | pixel art, 16-bit, crisp pixels, limited color palette | 宠物/趣味周边 | 0.8 |
| embroidery_lineart | 刺绣线稿 | embroidery style lineart, single color stitching texture, fabric feel | 宠物/简笔主体 | 0.7 |
| pop_art | 波普 | pop art, bold flat colors, halftone dots, high contrast comic style | 人像/宠物 | 0.7 |
| vintage_badge | 复古徽章 | vintage badge design, circular emblem, retro color palette, distressed texture | 宠物/纪念款 | 0.7 |
| ukiyoe | 浮世绘 | ukiyo-e style, japanese woodblock print, flat color areas, fine outlines | 风景/人像 | 0.6 |
| cross_stitch | 十字绣 | cross stitch pattern, grid stitches, embroidery fabric texture | 宠物/花卉 | 0.7 |
| sticker_cartoon | 贴纸卡通 | die-cut sticker style, thick white outline, flat vivid colors, simple shading | 宠物/元素提取 | 0.8 |

**维护规则**：新增风格必须先在 10 张测试图上验证保身份效果再入库；每个 style_id 附带 3 张效果样例存档。

## P8 身份保留短语表（identity_lock_phrase）

按主体类型选取，写进每一条正向 prompt。

| 主体类型 | 短语（英文） | 配套锁法 |
|---|---|---|
| 单人 | preserve exact facial features, face shape and hairstyle, identical person | InstantID/PuLID，weight 0.7–0.9 |
| 宠物 | preserve exact fur pattern, coat color and face markings, same pet | 参考图 embedding + IP-Adapter，weight 0.6–0.8；参考图 ≥2 张 |
| 多人 | each person keeps their own distinct facial features, no face swapping between subjects | 按 bbox 逐人注入，weight 0.7 |
| 人+宠 | both the person's facial features and the pet's fur pattern are preserved exactly | 双 embedding 分别注入 |
| 物体/无主体 | keep the original object's shape, color and details unchanged | ControlNet canny/depth，strength 0.6+ |

> 当前引擎（`scripts/gen.py` 垫图接口）下，"锁法"通过参考图数量 + prompt 短语落实；InstantID/IP-Adapter 等权重参数为未来自托管管线预留。

## P9 文字排版层

文字不进扩散模型。`scripts/text_layout.py` 接收以下 JSON，渲染成矢量文本层后叠到成品上。

```json
{
  "text_layers": [
    {
      "content": "文字内容，与用户确认稿逐字一致",
      "font": "字体文件路径或 assets/fonts 内的字体名",
      "size_pt": 72,
      "color": "#000000",
      "position": { "x_ratio": 0.5, "y_ratio": 0.85, "anchor": "bottom_center" },
      "layout": "single_line | auto_wrap | arc",
      "letter_fill_source": "letter_fill 模式下的拼字素材来源，如主体剪影"
    }
  ],
  "safe_area_ratio": 0.05,
  "render_output": "png_transparent"
}
```

**规则**：商用必须有字体授权记录（脚本默认使用 Windows 自带字体仅限内部打样）；输出优先矢量（当前版本输出透明底 PNG，矢量为后续版本）；渲染完成后由 P4 逐字比对。

## P10 宠物拟人重绘

S7 的典型场景；身份风险最高，锁法最重。单独调用与流程调用共用本模板。

```text
the {pet_breed} from the reference image as an anthropomorphic character,
wearing {costume}, {pose}, {scene_or_props},
{style_token},
preserve exact fur pattern, coat color and face markings, same pet,
{lighting}, {composition}, high quality, sharp details, print-ready

参数基线：
- 参考图 ≥2 张（不足 2 张时提示用户补传，不静默降质）
- 垫图模式下，把原图作为第一张参考图传入 gen.py --image
- 质检重点：花纹走向、毛色分区、耳朵形状（P4 的 score_basis 必须逐项覆盖）
```

## P11 套图一致性

S11/S12 的约束包，保证多张图"像同一个系列"。仅在产出为多图/系列时启用。

```text
套图约束（写进每张图的 prompt 与参数）：
1. 全部子图共用同一个 style_token、同一组 lighting 与 color palette 描述；
2. 同一主体所有子图共用同一组参考图，禁止中途换参考；
3. 构图槽位按子图角色变化：主图 centered composition / 侧图 rule of thirds / 细节图 close-up；
4. 尺寸按渠道预设：主图 1:1、详情 3:4、横幅 16:9，分辨率统一按交付标准（见 P14）。

一致性判定（交给 P4 执行）：
- 风格距离：各子图两两比对，风格一致性主观距离 < τ1（起点 0.15，由 P4 换算为打分）
- 主体区分度：同系列不同主体之间可明确区分 > τ2（起点 0.35）
- 双阈值同时满足才算 pass；任一项不满足，整组重跑而不是单张重跑
```

## P12 侵权与肖像权检查

对应能力 S2，可单独调用（批量扫图、风险自查），也是流程中的前置闸门。执行：`python scripts/mllm_task.py --task p12_compliance --image 待检图.jpg`

```text
你是图像处理系统的「合规检查员」。检查一张图片是否可以进入生成流程，或单独输出风险报告。

【检查项】
1. 是否包含可识别的品牌 logo、商标文字或近似变体；
2. 是否包含知名 IP 形象（动漫角色、影视角色、吉祥物等）或其明显变体；
3. 是否包含疑似非用户本人的第三方肖像；
4. 是否包含受版权保护的画作、摄影作品作为画面主体。

【输出字段】
{
  "verdict": "pass | need_declaration | block",
  "findings": [ { "type": "logo | ip_character | third_party_portrait | copyrighted_work",
                  "detail": "", "position": "" } ],
  "required_declaration": "verdict 为 need_declaration 时，需要用户勾选确认的声明文本"
}

【规则】
1. 含第三方肖像 → 至少 need_declaration，声明须包含"本人为肖像权人或已获授权"；
2. 含品牌 logo 或知名 IP → block，不进入生成流程，提示用户更换图片；
3. 拿不准时按 need_declaration 处理，宁可多问不可漏放；
4. 单独调用时本输出即最终报告；流程中调用时检查结果写入 Asset 元数据，随链路透传，供人工审核台复核。
```

## P13 元素提取指令

对应能力 S9。执行：`python scripts/element_extract.py --image 透明底图.png --type silhouette|paw_print|handwriting [--mask mask.png]`

```text
提取目标类型与处理路径（输入必须是带 alpha 通道的透明底 PNG，通常来自 S4 抠图的产出）：
- silhouette 轮廓剪影：主体 alpha 通道 → 填黑 → 边缘平滑（保留辨识度关键点）
- paw_print 爪印：在透明底图上按 alpha + 颜色聚类取肉垫区域 → 转单色剪影 → 边缘平滑 → 透明底输出
- handwriting 手写字：灰度阈值二值化 → 按 alpha 去底（当前版本输出位图，矢量化为后续版本）

硬约束：
- 禁止使用本地 ML 抠图模型（rembg/BRIA/u2net 等）做分割——历史实测边缘质量不达标；
  本技能一切分割均消费 S4 云端产出的 alpha 通道，或由用户/上游提供 mask。
- 输出 PNG（透明底）；同尺寸黑白预览图一并产出

质检点（交给 P4）：剪影与原主体轮廓重合度、爪印趾数正确（前5后4 常见，按原图为准）。
```

## P14 印刷交付检查

对应能力 S13。执行：`python scripts/delivery_check.py --input 成品.png [--target-width-mm 300] [--cmyk] [--text-safety-mm 5]`

```text
对成品文件逐项核验，输出 JSON：

{
  "file": "文件路径",
  "pixel_size": [宽, 高],
  "resolution_pass": <bool>,   // 按目标印刷尺寸计算 ≥300 DPI（默认 300mm 宽）
  "dpi": <数字>,
  "background": "transparent | solid | image",  // 印花稿要求 transparent
  "bleed_mm": <数字>,           // 需要裁切的物料留 3mm 出血（当前版本仅提示）
  "text_safety": <bool>,       // 文字距成品边缘 ≥5mm（需 agent 传入文本层位置）
  "defects": [],
  "verdict": "pass | fix_and_recheck"
}

规则：
1. 任一实物指标不达标，verdict 为 fix_and_recheck，并指明由哪个能力/原子修复；
2. RGB 文件在需要 CMYK 交付时（--cmyk），在 defects 中注明并给出转换提醒（荧光色系提示替代色）；
3. 检查结果随订单元数据存档。
```

## P15 玩法推荐排序器

可选启用。用户只传图不说话时，决定首屏推哪些能力卡片和流程卡片。执行：`python scripts/mllm_task.py --task p15_recommend --image 来图.jpg`

```text
你是图像处理系统的「玩法推荐排序器」。根据看图结果给能力/流程卡片排序。

【输入】看图理解器 JSON + 能力目录与流程目录
【输出】
{
  "ranked_items": [ { "item_id": "S或F开头", "item_type": "capability | playbook",
                      "reason": "一句话推荐理由", "confidence": <0~1> } ]
}

【排序规则】
1. 主体类型匹配优先：宠物图优先宠物相关能力与流程，全家福优先多人玩法；
2. 图片质量差（低清/模糊）时，优先推荐对清晰度容忍度高的风格（像素、贴纸卡通）；
3. 历史转化率作为次级权重，不覆盖主体匹配；
4. 推荐理由必须具体到来图内容（"这只柯基的花纹很适合圣诞拟人"），禁止通用话术。
```

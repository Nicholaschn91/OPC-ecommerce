# Agnes 引擎对接说明

> agnes-studio 自带完整生成引擎（2026-08-17 合并 agnes-image 入内，移除跨技能依赖）。
> 图像生成/垫图走 `scripts/gen.py`；多模态理解走 `scripts/mllm_task.py`。

## 依赖定位

- 技能目录：`~/.workbuddy/skills/agnes-studio/`（自身，含全部脚本与资源）。
- API Key：读 `~/.workbuddy/skills/agnes-studio/.env` 中 `AGNES_API_KEY`（.com 用）；`.cn` 用单独的 `AGNES_API_KEY_CN`。**两域是各自代理环境的令牌（两把不同 key），并非"同一把 key 两域通用"**。
- 无外部依赖：所有脚本都在本技能 `scripts/` 下，直接调用即可。

## 引擎能力边界（2026-08 文档核实）

- 图像端点仅一个：`POST /v1/images/generations`（文生图/图生图/多图合成），模型 `agnes-image-2.1-flash`。
- **无独立背景移除端点**：S4 抠图因此采用"云端生成键色图 + 本地确定性键色转 alpha"方案，
  且**禁止本地 ML 抠图模型**（rembg/BRIA/u2net，历史实测边缘不达标）。
- 理解端点：`POST /v1/chat/completions`，模型 `.cn` 用 `agnes-2.5-flash`、`.com` 用 `agnes-2.0-flash`。
- prompt 长度上限 10000 字符；生成结果尺寸用档位 `1K/2K/3K/4K` + `ratio`。

## 限流铁律（内部 gen.py）

1. 默认串行；并发不超过 3（`--concurrency`）。
2. 批量请求间隔 2–3s。
3. 429 自动暂停 60s 重试，最多 3 次。
4. 日限额 4000，`--usage` 查看，批量前自动预检。
5. RPM 分档：1K=20、2K=10、3K/4K=1。

## 端点 failover 与网络实测（需定期复测）

- **端点凭据与网络环境（2026-08-17 实测 + 08-17 勘误）**：两个端点凭据**均有效**，401 并非"令牌失效"，而是**当前运行时网络环境（代理开/关、出口 IP）与该端点预期环境不匹配**。
  - 模型：`.com`（apihub.agnes-ai.com）匹配"开代理/VPN、出口为境外 IP"；`.cn`（api.agnes-ai.cn）匹配"关代理、直连境内 IP"（且其结果强制 b64 内联以避开 Google 图床）。**两域是各自环境的令牌（两把不同 key），并非"同一把 key 两域通用"**——`.cn` 只认 `.cn` 的令牌，用 `.com` 的 key 打 `.cn` 必 401；域名的"能否连上"才取决于出口 IP/代理状态。
  - 08-17 实测当时代理开着 → `.com` 返回 200、`.cn` 返回 401。这是"环境不匹配"而非"`.cn` 坏了"；若当时关掉代理，则 `.cn` 会认证通过、`.com` 反而可能 401。
  - `mllm_task.py` 一直默认 **.com 优先**（2026-08-16 起），在代理开着时正确。
  - `gen.py` / `alt.py` **原默认 `.cn` 主用且 401 时直接 `sys.exit`**（不 failover）—— 这是真 bug：代理开着时直接死在 `.cn` 401，没机会切到能用的 `.com`。
    **2026-08-17 已修复**：默认改为 `.com` 主用，且 401/403 与网络/5xx 一样触发 failover（任一端点报错自动用另一个）。**同日再修双令牌**：failover 原本"一把 key 两域通用"，与"两把令牌对应两种代理环境"的现实不符——改为 `.com` 用 `AGNES_API_KEY`、`.cn` 用 `AGNES_API_KEY_CN`，未配置回退主 key。failover 机制现兼具"双端点双令牌容错"与"自动适配当前代理状态"双重作用。
  - 主备顺序可用 `AGNES_BASE_URL`（主）/ `AGNES_FALLBACK_URL`（备）覆盖；若常用关代理环境，可把它俩对调让 `.cn` 主用，减少一次 failover 往返。
- 2026-07-28 实测：`.cn` 曾出现 Cloudflare 504（源站不可达）；`.com` 国内无 VPN 被 SNI 重置。
  本次（08-17）`.com` 在开启 TUN/VPN 的国内网络直连成功，说明网络策略可能有变化——以实际运行结果为准。
- `.cn` 图像结果强制 b64_json 内联（结果图床在 Google 域名，国内被墙）。
- 顺序可用 `AGNES_BASE_URL`（主）/ `AGNES_FALLBACK_URL`（备）覆盖。
- **已知缺口 A**：`gen.py` 的 `--size` 仅接受显式 `WxH`（如 2048x1536），**未暴露文档声称的 `size:"1K" + ratio:"2:3"` 档位/比例语法**；多档位以显式尺寸覆盖（1K/2K/3K/4K 均在 `SIZE_CHOICES`）。如需比例档位需补 `--ratio` 参数。
- **已知缺口 B**：`gen_video.py` 端点缺口：仅 `.com`，未做 `.cn` failover（与 `gen.py`/`alt.py` 双端点不一致）。

## gen.py 调用约定（本技能统一）

```bash
# 定位 agnes-studio
STUDIO=~/.workbuddy/skills/agnes-studio

# 文生图（S1）
python "$STUDIO/scripts/gen.py" --prompt "<P6填充结果>" --size 2048x2048 --output out.png

# 垫图/多图（S3/S4/S5/S6/S7/S8/S11/S12）
python "$STUDIO/scripts/gen.py" --prompt "<P6填充结果>" --image 原图1.png [--image 参考图2.png] --size 2048x2048 --output out.png
```

注意：

- gen.py 只接受单条 prompt；P3 输出的"negative_prompt"在本引擎下合并为 prompt 尾部 avoid 语句。
- `--size` 用旧精确写法（gen.py SIZE_CHOICES），如 2048x2048、1536x2048、1024x1024。
- 生成前必须已读 SKILL.md 的 API 细节章节（response_format 位置铁律等）。

## mllm_task.py 调用约定（本技能自带）

走 chat/completions 端点，图片以 base64 data URI 内联（缩到 768px 内）：

```bash
python scripts/mllm_task.py --task p1_understand --image 来图.jpg [--intent "用户原话"] [--capability S6]
python scripts/mllm_task.py --task p12_compliance --image 待检图.jpg
python scripts/mllm_task.py --task p4_check --image 原图.jpg --result-image 结果.jpg --user-file goal.json
python scripts/mllm_task.py --task p0_route --user-file request.json
python scripts/mllm_task.py --task p5_copy --user-file brief.json
python scripts/mllm_task.py --task p15_recommend --image 来图.jpg
```

输出：stdout 打印解析后的纯 JSON；解析失败（模型未按 JSON 输出）自动重试一次并在提示词中强调"只输出 JSON"。

> **视频端点同样接受 base64**：`/v1/videos` 的 `image`（图生视频）与 `extra_body.image`（关键帧）字段接受 base64 `data:` URI，无需图床 URL（2026-08-17 实测：64×64 图内联成功生成 mp4）。`gen_video.py` 已内置"本地路径自动转 base64"逻辑。

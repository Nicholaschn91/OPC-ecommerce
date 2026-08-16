# 人工交接卡 · S3-04 终版优化（Qwen3.8-Max 网页端）

本目录是半自动流程里「人跑模型」这一步的固定落点。

## 你要做的 4 步

1. 打开同目录 `prompt_to_run.txt`，**全选复制全部内容**。
2. 打开 Qwen3.8-Max 网页端（qianwen.com / tongyi.aliyun.com），把内容**粘贴进对话框 → 发送**。
3. 模型会连续输出 Step1→5 + 末尾 `BASE_MATERIAL` 块。把**从「Step 1」到 `BASE_MATERIAL` 结束的整段**复制。
4. 回到本目录，打开 `clean.md`，**贴到首行注释之下**，保存。然后告诉 agent：「跑 S3-04 校验」。

## agent 接下来会做

- 用 `verify-ledger.py` 跑闸门（防蚕食唯一性 + 三级熔断 + 字段回读 + 软层 review）。
- 无 MELTDOWN/CRITICAL_STOP 后，按 SHARED_CONTEXT append/merge 语义写飞书（须你逐条授权）。

## 参考物料

- `listing_bundle.json`：Stage1 产物（词策略蓝图）。
- `S3-04_etsy_v1.md`：初版草稿（若存在）。
- 自动路径（playwright-qwen 注入）不走本目录，由 build-inject.py 产出 .js 片段。

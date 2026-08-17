# ⛔ 已废弃：手搓 Playwright 脚本

本目录下的脚本（`optimize-one.js` / `optimize-batch.js` / `sync-cookies.py`）实现的是
**自起 Chromium（`playwright-core` + `chromium.launchPersistentContext`）+ 复用 profile 登录态**
的浏览器自动化方案。

## 为什么废弃
用户于 **2026-08-08** 立下「浏览器控制铁律」：
> 凡需控制浏览器（打开网页、点击、填表、截图、抓取、注入等），**唯一合法手段是浏览器类 MCP**
> （如 `browser-qwen` MCP）。**严禁手写或运行 Playwright/Chrome 自动化脚本**。

手搓脚本会：
1. 绕开已登录的 MCP 会话；
2. 与 MCP 争抢同一 `cdp-profile-h` 的 Chrome 单例锁；
3. 无法复用用户已验证的 MCP 恢复姿势。

故本目录脚本一律**禁止使用**，仅作历史参考保留。

## 现行替代方案（见 SKILL.md）
浏览器全程走 **`browser-qwen` MCP**，由 skill 的 MCP 驱动 recipe 控制：
- 注入：`scripts/build-inject.py` 生成 `browser_run_code_unsafe` 片段 → `page.keyboard.insertText` 注入 contenteditable 输入框
- 抓取：MCP `download` 事件捕获 Blob 下载
- 清洗：`scripts/clean-capture.py`
- 结构化：`scripts/extract-clean.js`（纯文件处理，不涉及浏览器，保留）

## 登录态维护
登录态现由 `browser-qwen` MCP 的 `cdp-profile-h` 承载。若 cookie 过期：
打开 qianwen.com/chat（经 MCP 浏览器）→ 手动登录一次 → 会话持久化在 profile 内。
`sync-cookies.py` 的「Tabbit 解密→重加密注入」机制已不再适用，废弃。

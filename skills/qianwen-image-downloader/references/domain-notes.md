# 千问无水印原图 —— 领域笔记（实测）

## 关键事实（2026-08 实测，已登录浏览器真机验证）

在用户已登录的 `www.qianwen.com/chat` 生成一张图，嗅探脚本捕获到 **466 个图片 URL**：
- **458 个无水印原图**：
  - `gw.alicdn.com/...-0-tps-1024-1024.jpg` —— 阿里图床原图，URL 带尺寸标记 `-0-tps-1024-1024`，无处理参数
  - `yes-file.uc.cn/file/...png` —— UC 网盘原图，无扩展名、无水印参数（早期版本漏收，已在 `content.js` 的 `IMG_HOSTS` 补 `uc.cn, yes-file`）
- **8 个带水印展示图**：
  - `quark-aistudio-cdn.quark.cn/...?auth_key=...&x-oss-process=image/format,webp/resize,s_800` —— 页面展示用的衍生图

结论：**接口同时给「无水印原图」和「带水印展示图」两套地址**，原生可抓干净原图，无需后处理去水印。

## 域名速查

| 域名 | 角色 | 是否原图 |
|---|---|---|
| `gw.alicdn.com` | 阿里图床 | ✅ 无水印原图 |
| `yes-file.uc.cn` | UC 网盘 | ✅ 无水印原图（无扩展名） |
| `quark-aistudio-cdn.quark.cn` | 夸克 AI 衍生 CDN | ❌ 带水印（含 `x-oss-process`） |

`manifest.json` / `content.js` 的白名单与 `host_permissions` 已覆盖上述域名。

## 与豆包工具的差异

| 维度 | 豆包 doubao-downloader | 本千问工具 |
|---|---|---|
| 注入范围 | 写死 `doubao.com/chat/*` | `qianwen.com/*` + `tongyi.aliyun.com/*` |
| 取图方式 | 劫持 JSON.parse 找私有字段 `image_ori_raw.url` | 通用嗅探（hook fetch/XHR + DOM 扫描），不赌字段名 |
| 抗改版 | 弱（依赖私有字段名） | 较强（按 URL 特征过滤水印） |
| 去水印 | 真取原图 | 真取原图（千问主动返回） |

## 反爬 / 网络

- 千问对话页会重定向：`tongyi.aliyun.com/chat` → `www.qianwen.com/chat`。`QW_URL` 直接用后者即可。
- 本机有系统代理 `127.0.0.1:7897`（注意末尾**不要**带斜杠，否则 Chrome 报 `ERR_NO_SUPPORTED_PROXIES`）。
- 直连 `tongyi.aliyun.com` 返回 200，但浏览器默认读 Windows 系统代理；Playwright 显式传 `proxy` 选项最稳。
- IP 铁律**只针对 Etsy**，千问不在此限，可直连/走本地代理。

## 已知坑

1. `launchPersistentContext` 不能用 `--user-data-dir` 参数（Playwright 报错），改用 `userDataDir` 选项（即本 CLI 的 `PROFILE` 目录）。
2. 有头模式才能看到登录界面；无头模式需依赖已登录的持久 profile 才能自动生成图。
3. `generate` 的输入框定位（`textarea` 优先，其次 `contenteditable`）若千问改版需调整。
4. 下载用 `curl` 而非 node 直连，规避跨域/代理/鉴权问题；curl 在本机 git-bash / Win10+ 自带。

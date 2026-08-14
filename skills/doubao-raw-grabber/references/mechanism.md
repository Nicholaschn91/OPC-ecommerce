# 去水印原图抓取机制说明

## 背景：页面 `<img>` 给的是带水印图

豆包聊天界面渲染生成图时，`<img>.src` 指向：

```
https://p<N>-flow-imagex-sign.byteimg.com/tos-cn-i-a9rns2rl98/rc_gen_image/<hash>.jpeg
  ~tplv-a9rns2rl98-ds_wm_1_6_marc_b_3_dk:RG91YmFvMDIxTk5BMDAxMjYwNzMxMk5O.png?<签名>
```

- `ds_wm_1_6_marc_b_3` = 图片服务（ImageX）的**画水印**变换指令；
- `dk:RG91...` 是账号水印文本（base64 解出为 `Doubao021...NO`）。

实测：直接剥掉 `~tplv-...` 水印段 → 签名失效 **HTTP 403**；带水印原样下载只有 ~16 KB（缩略水印版）。
所以「抓 `<img>` 地址」拿不到干净图。

## 真相：原图在对话接口 JSON 里

开源扩展「豆包下载器」(`doubao-downloader`) 源码核心逻辑：

```js
// dist/doubao-downloader.user.js:56636
const rawImage = image.image_ori_raw?.url;
if (rawImage && !rawImage.includes("watermark")) { ... }
```

即每条消息结构 `creation.image.image_ori_raw.url` 才是无水印原图地址，变换段为 `ppe_image_raw_marc_b_3`（**不画水印**）：

```
.../rc_gen_image/<hash>.jpeg~tplv-a9rns2rl98-ppe_image_raw_marc_b_3:RG91...png?<签名>
```

该地址与页面 `<img>` 在**同一 CDN、同一签名体系**，仅变换段不同 → 直接可下载全分辨率原图。

## 本工具做法（不依赖插件 UI）

1. 浏览器层 `page.on('response')` 拦截所有 `content-type: json` 的响应；
2. `JSON.parse` 后递归查找 key `image_ori_raw` → 收集其 `.url`；
3. 去重，写入 `<out>/<convId>/raw_urls.txt`；
4. 机器侧 `fetch`（带 `Referer: https://www.doubao.com/`）逐张下载，绕过浏览器 CORS。

实测对照（对话 `chat/38436368378934786`）：

| 来源 | 数量 | 单张大小 | 结论 |
|------|------|----------|------|
| 页面 `<img>`（带水印） | — | ~16 KB | 缩略水印版 |
| 本工具抓取（image_ori_raw） | 5 | 3.5–5 MB | 全分辨率无水印原图 ✓ |

所有抓取 URL 均不含 `ds_wm` 水印段，确为无水印原图。

## 为什么有头/无头都成立

- 登录态在共享 `--user-data-dir` profile（cookie 文件），与是否有头无关；
- 抓 raw 是网络/JS 层机制，不依赖插件浮动按钮的可见点击；
- 真正落盘下载是机器侧，与浏览器模式彻底解耦。

唯一例外：交互式重新登录必须回有头（无头无法扫码/输验证码）。

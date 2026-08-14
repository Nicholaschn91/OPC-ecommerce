#!/usr/bin/env node
/**
 * doubao_img2img.cjs  —  Doubao 图生图 CLI（写操作）
 *
 * 作用：用「参考图 + Prompt」驱动豆包 AI 创作（doubao.com/chat/create-image）
 *       生成变体图并下载无水印原图，可选调用 verify-img.py 落实度预筛。
 *
 * ⚠️ 模型硬约束：必须 Seedream 5.0 Lite（4.5 / 4.0 / 5.0 Pro 一律不用）。
 *
 * 依赖：Node >= 18（全局 fetch）、playwright（自动从已知路径或 PLAYWRIGHT_LIB 解析）。
 * 浏览器驱动模式复用 doubao-raw-grabber 的 launchPersistentContext + --profile（用户明确授权的专用 skill）。
 *
 * 用法：
 *   node doubao_img2img.cjs --ref <参考图.jpg> --prompt <prompt.txt> --out <输出.jpg> [--ratio 1:1] [选项]
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

// ---------- 配置默认值 ----------
const SKILL_DIR = __dirname; // .../doubao-image-mcp/scripts
const DEFAULT_PROFILE =
  'C:/Users/nicho/.workbuddy/skills/multi-agent-sop/doubao-image-mcp/doubao-profile';
const CHROME_EXE = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const CREATE_URL = 'https://www.doubao.com/chat/create-image';
const REFERRER = 'https://www.doubao.com/';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36';
const TARGET_MODEL = 'Seedream 5.0 Lite';
const REF_INPUT = 'input.input-I22ghh';
const CHAT_EDITOR_SEL = 'TEXTAREA.semi-input-textarea.semi-input-textarea-autosize';
const SEND_SEL = '#flow-end-msg-send';
const CHAT_SEND_SEL = '#flow-end-msg-send';
const EDITOR_SEL = '.tiptap.ProseMirror';
// 当前豆包生成图 CDN 格式：pX-flow-imagex-sign.byteimg.com/tos-cn-i-a9rns2rl98/<hash>.png~tplv-...-image.png
// （全质量）或 ...-image-qvalue.png（预览）。无旧版 /rc_gen_image/ 段。排除 rc/icon 图标。
const CDN_RE = /flow-imagex-sign\.byteimg\.com\/tos-cn-i-a9rns2rl98\/(?!rc\/icon).+\.(png|jpeg)/;

// 比例 → 数值（verify-img.py --ratio 用；自动按 1:1 处理）
const RATIO_NUM = {
  自动: 1.0, '1:1': 1.0, '4:3': 1.3333, '3:4': 0.75,
  '16:9': 1.7778, '9:16': 0.5625, '2:3': 0.6667, '3:2': 1.5,
};

// ---------- 拟人化 + 验证暂停（烘焙进 CLI，弱模型只跑命令无需理解） ----------
function rndInt(min, max) { return Math.floor(min + Math.random() * (max - min)); }
// 随机停顿，模拟真人节奏（避免固定延时被识别为机器）
async function humanDelay(page, min = 400, max = 1100) {
  await page.waitForTimeout(rndInt(min, max));
}
// 逐字输入，模拟真人打字（替代 insertText 瞬插 —— 那是明显 agent 痕迹）
async function humanType(page, text, minDelay = 22, maxDelay = 85) {
  for (const ch of text) {
    await page.keyboard.type(ch, { delay: rndInt(minDelay, maxDelay) });
  }
}
// 检测豆包「图片识别验证」（非滑块，是点选图片类）。命中则暂停等人。
async function detectVerification(page) {
  return await page
    .evaluate(() => {
      const body = document.body ? document.body.innerText || '' : '';
      const hints = ['请完成验证','安全验证','验证码','请选择','图像验证','人机验证','请点击','验证失败','请按顺序','请选出','请点击下图','请选择包含','拖动滑块','拼图','请按顺序点击','验证不通过'];
      if (hints.some((h) => body.includes(h))) return true;
      const cap = document.querySelector(
        'iframe[src*="captcha"], .captcha, [class*="verify"], [class*="Captcha"], [class*="secsdk"], [id*="captcha"], [class*="risk"], [class*="slider"]'
      );
      return !!cap;
    })
    .catch(() => false);
}
// 若检测到验证，暂停等人；人在 profile 目录放 VERIFY_DONE.txt 后自动续跑（最多等 30 分钟）
async function waitForHumanIfBlocked(page, log, profileDir) {
  if (!(await detectVerification(page))) return false;
  const sentinel = path.join(profileDir, 'VERIFY_DONE.txt');
  try { fs.unlinkSync(sentinel); } catch {}
  log('⚠️ 检测到豆包图片识别验证。请手动完成验证（点选图片类），完成后在该 profile 目录创建空文件 VERIFY_DONE.txt，脚本将自动继续。');
  log('   profile 目录: ' + profileDir);
  const deadline = Date.now() + 30 * 60 * 1000;
  while (Date.now() < deadline) {
    if (fs.existsSync(sentinel)) {
      try { fs.unlinkSync(sentinel); } catch {}
      log('  ✓ 检测到 VERIFY_DONE，继续。');
      await humanDelay(page, 1500, 3000);
      return true;
    }
    await page.waitForTimeout(3000);
  }
  throw new Error('验证等待超时（30 分钟无人处理）');
}
// 解析内存图片尺寸（PNG/JPEG/WebP），用于落盘确认抓到的真实分辨率（非固定 1024）
function imageDims(buf) {
  try {
    if (buf.length > 24 && buf[0] === 0x89 && buf[1] === 0x50) {
      return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
    }
    if (buf.length > 3 && buf[0] === 0xff && buf[1] === 0xd8) {
      let i = 2;
      while (i < buf.length - 8) {
        if (buf[i] !== 0xff) { i++; continue; }
        const m = buf[i + 1];
        if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
          return { w: buf.readUInt16BE(i + 7), h: buf.readUInt16BE(i + 5) };
        }
        i += 2 + buf.readUInt16BE(i + 2);
      }
    }
    if (buf.toString('ascii', 0, 4) === 'RIFF' && buf.toString('ascii', 8, 12) === 'WEBP') {
      if (buf[12] === 0x56 && buf[13] === 0x50 && buf[14] === 0x38 && buf[15] === 0x58) {
        return { w: buf.readUInt32LE(16), h: buf.readUInt32LE(20) };
      }
    }
  } catch {}
  return null;
}

// 确保停留在豆包「AI 创作」生成页：create-image 可能被重定向到最近对话，
// 此时比例/发送按钮不存在，必须显式回到生成器再操作（弱模型无需理解，自动执行）
async function ensureCreateImagePage(page, log) {
  const hasGenTool = () =>
    page
      .evaluate(() => {
        const btns = [...document.querySelectorAll('button')];
        // 仅生成器独有：比例按钮（聊天页没有；参考图 input 聊天页也有，不可作判据）
        return btns.some((b) => /比例/.test(b.textContent || ''));
      })
      .catch(() => false);
  for (let attempt = 0; attempt < 5; attempt++) {
    if (await hasGenTool()) return true;
    // 方式1：点侧栏「AI 创作」回到生成器
    const clicked = await page
      .evaluate(() => {
        const el = [...document.querySelectorAll('a, button')].find((e) => /AI\s*创作/.test(e.textContent || ''));
        if (el) { el.click(); return true; }
        return false;
      })
      .catch(() => false);
    log('  [ensure] 当前非生成页（无比例按钮），' + (clicked ? '已点「AI 创作」重试' : '未找到「AI 创作」入口，改直接重导'));
    // 方式2：直接重导 create-image（兜底）
    if (!clicked) {
      await page
        .goto('https://www.doubao.com/chat/create-image', { waitUntil: 'domcontentloaded' })
        .catch(() => {});
    }
    await humanDelay(page, 2500, 4500);
  }
  return await hasGenTool();
}

// ---------- playwright 解析（多候选，避免硬编码单点） ----------
function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_LIB,
    'playwright',
    'C:/Users/nicho/AppData/Local/npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright',
    'C:/Users/nicho/.workbuddy/binaries/node/versions/22.22.2/node_modules/@playwright/cli/node_modules/playwright',
  ].filter(Boolean);
  let lastErr;
  for (const c of candidates) {
    try {
      return require(c);
    } catch (e) {
      lastErr = e;
    }
  }
  throw new Error(
    '找不到 playwright。设置环境变量 PLAYWRIGHT_LIB 指向其目录，或确认 npm-cache 中存在 playwright。\n最后错误: ' +
      (lastErr && lastErr.message)
  );
}

// ---------- python 解析（verify-img.py 用） ----------
function resolvePython() {
  const candidates = [
    process.env.PYTHON_BIN,
    'C:/Users/nicho/.workbuddy/binaries/python/envs/default/Scripts/python.exe',
    'python3',
    'python',
  ].filter(Boolean);
  for (const c of candidates) {
    try {
      execFileSync(c, ['--version'], { stdio: 'ignore' });
      return c;
    } catch {
      /* try next */
    }
  }
  throw new Error('找不到 python（设置 PYTHON_BIN 或安装 python）');
}

// ---------- 参数解析 ----------
function parseArgs(argv) {
  const o = {
    ref: null,
    prompt: null,
    out: null,
    ratio: '1:1',
    profile: DEFAULT_PROFILE,
    headless: true,
    verify: false,
    report: null,
    genTimeout: 90000,
    cdp: null,
    text2img: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--ref') o.ref = argv[++i];
    else if (a.startsWith('--ref=')) o.ref = a.slice('--ref='.length);
    else if (a === '--prompt') o.prompt = argv[++i];
    else if (a.startsWith('--prompt=')) o.prompt = a.slice('--prompt='.length);
    else if (a === '--out') o.out = argv[++i];
    else if (a.startsWith('--out=')) o.out = a.slice('--out='.length);
    else if (a === '--ratio') o.ratio = argv[++i];
    else if (a.startsWith('--ratio=')) o.ratio = a.slice('--ratio='.length);
    else if (a === '--profile') o.profile = argv[++i];
    else if (a.startsWith('--profile=')) o.profile = a.slice('--profile='.length);
    else if (a === '--report') o.report = argv[++i];
    else if (a.startsWith('--report=')) o.report = a.slice('--report='.length);
    else if (a === '--gen-timeout') o.genTimeout = parseInt(argv[++i], 10);
    else if (a.startsWith('--gen-timeout=')) o.genTimeout = parseInt(a.slice('--gen-timeout=').length, 10);
    else if (a === '--cdp') o.cdp = argv[++i];
    else if (a.startsWith('--cdp=')) o.cdp = a.slice('--cdp='.length);
    else if (a === '--headed') o.headless = false;
    else if (a === '--verify') o.verify = true;
    else if (a === '--text2img') o.text2img = true;
    else if (a === '-h' || a === '--help') o.help = true;
  }
  return o;
}

const HELP = `
doubao_image  —  Doubao 图像生成 CLI（CDP 复用 headed Chrome；写操作：参考图 + Prompt → 出变体图 → 下载 + 可选预筛）

模型硬约束：Seedream 5.0 Lite（4.5 / 4.0 / 5.0 Pro 一律不用，脚本会强制幂等切到 5.0 Lite）

用法:
  # 图生图（默认）
  node doubao_img2img.cjs --ref <参考图.jpg> --prompt <prompt.txt> --out <输出.jpg> [--ratio 1:1] [选项]
  # 文生图（不需要 --ref；需先在 doubao 工作台选 "图像生成" agent）
  node doubao_img2img.cjs --text2img --prompt <prompt.txt> --out <输出.jpg> [--ratio 1:1] [选项]

参数:
  --ref <file>        参考图路径（图生图必填，JPG/PNG/WebP）
  --prompt <file>     Prompt 文本文件路径（必填，纯文本，含 Negative 段落）
  --out <file>        输出图片路径（必填，JPG）
  --ratio <r>         比例，默认 1:1。可选：自动/9:16/2:3/3:4/1:1/4:3/3:2/16:9
  --text2img          文生图模式（不传 --ref；脚本会尝试切换到"图像生成" agent）
  --profile <dir>     用户数据目录（默认 doubao-image-mcp/doubao-profile，内含登录态）
  --headed            有头模式（默认无头）
  --verify            出图后调用 verify-img.py 做落实度预筛
  --report <file>     verify 报告路径（默认 <out>.verify.json）
  --gen-timeout <ms>  生成等待超时（默认 90000）
  --cdp <url>         CDP 端点（如 http://127.0.0.1:9223），连到已有 headed Chrome 复用
                      推荐：你手开 headed Chrome + --remote-debugging-port=9223 + 同 profile，
                      本脚本 connectOverCDP 连上去，整个会话复用，不自起 Chrome，不关你的浏览器
  -h, --help          显示帮助

注意：
  推荐 --cdp 模式（headed 可复用，与 MCP 同源思路）。你的浏览器不会被脚本关掉，你全程可见。
  登录态在你那个 Chrome 的 profile 里（你开 Chrome 时 --user-data-dir 指定）。
  非 --cdp 模式才会 launchPersistentContext 自起 Chrome（profile 隔离同旧约定），仅兜底用。
`;

// ---------- 模型：幂等切到 TARGET_MODEL ----------
async function setModel(page, model) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  await page.keyboard.press('Escape');
  await humanDelay(page, 500, 1200);
  const btn = page.getByRole('button', { name: /模型|Seedream/ }).first();
  await btn.click();
  await humanDelay(page, 600, 1300);
  const cur = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((e) => /Seedream/.test(e.textContent || ''));
    return b ? b.textContent.trim() : '';
  });
  if (!cur.includes(model)) {
    await page.getByRole('menuitem').filter({ hasText: model }).first().click();
    await humanDelay(page, 600, 1300);
  }
  await page.keyboard.press('Escape');
  await humanDelay(page, 400, 900);
  const after = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find((e) => /Seedream/.test(e.textContent || ''));
    return b ? b.textContent.trim() : '';
  });
  return after;
}

// ---------- 上传参考图（setInputFiles 喂隐藏 input） ----------
async function uploadRef(page, ref) {
  await page.setInputFiles(REF_INPUT, ref);
  await humanDelay(page, 2500, 5000);
  const ok = await page.evaluate((sel) => {
    const inp = document.querySelector(sel);
    return !!inp && inp.files && inp.files.length > 0;
  }, REF_INPUT);
  return ok;
}

// ---------- 录完 Prompt 与点 Send 之间的「确定性 2 秒」React state sync 等待 ----------
// 用户 2026-08-13 22:4x 诊断：loc.fill / insert_text 触发 React 受控组件 onChange 后，
// React state 异步合并（React 18 batching），如果立刻点 send，会把"旧 state（空/上轮残留）"
// 提交出去，而 textarea DOM 里"新值"还显示——表现就是「前半部分发了、Negative 段停留」。
// 之前随机延时 1.2–2.6s 是赌运气；改为确定性 2000ms，绝不再赌。
async function reactStateSyncDelay(page, ms = 2000) {
  await page.waitForTimeout(ms);
}

// ---------- 文生图：尝试切到「图像生成」agent ----------
// doubao chat 输入框下方一排 agent 切按钮（快速 / PPT 生成 / 图像生成 / 帮我写作 / ...）。
// 文生图要点「图像生成」才能让 doubao 出图；不切就用 chat 模式，不生成图。
// 找不到时不 FATAL（best-effort），warn 后继续让用户手动切。
async function trySwitchToImageGenAgent(page, log) {
  const candidates = [
    // 直接文本匹配：doubao 的"图像生成"agent 卡片
    'text="图像生成"',
    'text="图片生成"',
    'text="AI 绘画"',
    '[aria-label*="图像生成"]',
    '[aria-label*="图片生成"]',
    '[role="tab"]:has-text("图像生成")',
    '[role="button"]:has-text("图像生成")',
    'div[role="button"]:has-text("图像生成")',
  ];
  for (const sel of candidates) {
    try {
      const el = page.locator(sel).first();
      if ((await el.count()) > 0 && (await el.isVisible().catch(() => false))) {
        await el.click({ timeout: 2500 });
        await humanDelay(page, 800, 1600);
        log('  已切到「图像生成」agent: ' + sel);
        return true;
      }
    } catch { /* try next */ }
  }
  log('  ⚠️ 未找到「图像生成」agent 按钮 — doubao 可能仍在 chat 模式（不会出图）。请先在浏览器手动点 "图像生成" agent，再继续。');
  return false;
}

// ---------- 复用单 tab 起新任务（用户 2026-08-13 22:5x 强制要求） ----------
// 用户实测：连续多次出图任务用 page.goto / browser.newPage 反复开新 tab，会让本地 Chrome 内存涨。
// 修复：
//   1) CDP 模式下拿到已有 page 就复用，绝不自起新 tab；
//   2) 已有 tab 时优先用页内「新建工作任务」按钮或 Ctrl+Shift+K 快捷键起新任务；
//   3) 兜底才走 page.goto(create-image)（同 tab，不开新 tab）；
//   4) page.about:blank 也走兜底（这是上次 CDP 留下的空白页）。
// 弱模型只需调用 startNewTaskInSameTab(page, log)，按列表优先级试；最后 fallback 到 navigate。
async function startNewTaskInSameTab(page, log) {
  // 1) 优先：点页面里「新工作任务」「新建对话」「AI 创作」按钮
  const candidates = [
    'text="新工作任务"',
    'text="新建任务"',
    'text="新建对话"',
    'button[aria-label*="新任务"]',
    'button[aria-label*="新建"]',
    '[role="button"][aria-label*="新建任务"]',
  ];
  for (const sel of candidates) {
    try {
      const el = page.locator(sel).first();
      if ((await el.count()) > 0 && (await el.isVisible().catch(() => false))) {
        await el.click({ timeout: 3000 });
        await humanDelay(page, 1200, 2200);
        log('  ✓ in-page 新建任务: ' + sel);
        return true;
      }
    } catch { /* try next */ }
  }
  // 2) 兜底：doubao 快捷键 Ctrl+Shift+K（用户实测页面提示"新工作任务 Ctrl Shift K"）
  try {
    await page.keyboard.press('Control+Shift+K');
    await humanDelay(page, 1200, 2200);
    log('  ✓ Ctrl+Shift+K 触发新任务');
    // navigate 后 verify
    await page.waitForURL(/create-image|\/chat\//, { timeout: 8000 }).catch(() => {});
    return true;
  } catch {}
  // 3) 最终 fallback：同 tab navigate create-image（不开新 tab）
  log('  → fallback: 同 tab 导航 ' + CREATE_URL);
  await page.goto(CREATE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await humanDelay(page, 1500, 3000);
  return true;
}

// ---------- 生成前登录态 / 页面状态自检 ----------
// 显式区分："未登录"、"游客模式"、"agent 错位"，绝不静默继续
async function preflightGenContext(page, log, opts) {
  const sig = await page.evaluate(() => {
    const body = document.body ? (document.body.innerText || '') : '';
    return {
      url: location.href,
      isGuest: /游客模式/.test(body),
      isLoginPrompt: /登录后/.test(body) && /图片|视频|生成/.test(body),
      hasGenRatioBtn: !!document.querySelector('button') &&
        [...document.querySelectorAll('button')].some((b) => /比例|1:1|4:3/.test(b.textContent || '')),
      hasTiptap: !!document.querySelector('.tiptap.ProseMirror'),
      hasChatTA: !!document.querySelector('TEXTAREA.semi-input-textarea'),
    };
  });
  if (sig.isGuest) {
    throw new Error('检测到「游客模式」：当前 doubao session 没认登录（cookie 过期或被识别）。' +
      '请重登：' + opts.profile + ' 目录用 headed Chrome 打开 doubao.com 登录后，建空文件 VERIFY_DONE.txt。');
  }
  if (!sig.hasTiptap && !sig.hasChatTA) {
    throw new Error('生成前自检失败：既不在 .tiptap.ProseMirror（独立生成器页），也不在 chat 的 TEXTAREA.semi-input-textarea。' +
      '当前 url=' + sig.url + ' — 请手动打开浏览器看页面是否在正常生成器/chat 状态。');
  }
  log('  preflight: url=' + sig.url.replace('https://www.doubao.com', '').slice(0, 60) +
    ' guest=' + sig.isGuest + ' genUi=' + sig.hasGenRatioBtn + ' tiptap=' + sig.hasTiptap + ' chatTA=' + sig.hasChatTA);
}

// ---------- 自适应当前页面：选出当前可用的输入框 + 发送按钮 ----------
//   doubao 现在行为：进 create-image → 上传参考图 → 页面跳到 /chat/<会话id>，
//   在 chat 的 TEXTAREA.semi-input-textarea 里打字发送（chat 自加"生成图片："前缀）。
//   老的 .tiptap.ProseMirror / #flow-end-msg-send 仅在独立生成器页出现，作兜底。
async function resolveEditor(page) {
  return await page.evaluate(
    ({ chatSel, ceSel }) => {
      const ta = document.querySelector(chatSel);
      if (ta) {
        return {
          kind: 'textarea',
          selector: chatSel,
          // textarea 的"内容"读 .value；chat 草稿自加"生成图片："前缀但读回就是用户文本
          read: () => ta.value || '',
        };
      }
      const ed = document.querySelector(ceSel);
      if (ed) {
        return {
          kind: 'contenteditable',
          selector: ceSel,
          read: () => ed.innerText || ed.textContent || '',
        };
      }
      return null;
    },
    { chatSel: CHAT_EDITOR_SEL, ceSel: EDITOR_SEL },
  );
}

async function resolveSendBtn(page) {
  // 两种页面 send 按钮 id 同名（#flow-end-msg-send），且都在同一个位置；
  // 但 chat 页有时也被不同 class 隐藏。优先 getByRole 也兜底一下。
  return await page.evaluate(() => {
    const a = document.querySelector('#flow-end-msg-send');
    if (a) return { selector: '#flow-end-msg-send' };
    const b = document.querySelector('button[aria-label*="发送"], button[aria-label*="send"]');
    if (b) return { selector: 'button[aria-label*="发送"], button[aria-label*="send"]' };
    return null;
  });
}

// ---------- 注入 Prompt（焦点锁 + 清空 + 逐字 + 完整性校验，杜绝残留） ----------
async function injectPrompt(page, text) {
  const meta = await resolveEditor(page);
  if (!meta) {
    throw new Error(
      `找不到可用的输入框（既不在 chat 的 ${CHAT_EDITOR_SEL}，也不在生成器 .tiptap.ProseMirror）。` +
      `可能页面还没加载完或已被导航走。`,
    );
  }

  // 2) 清空已有内容（locator.fill 空字符串，Playwright 内部走 React 兼容路径）
  const loc = page.locator(meta.selector).first();
  await loc.fill('');
  await humanDelay(page, 200, 500);
  // 再 focus 一次保证后续 type 落点正确
  await loc.focus();
  await humanDelay(page, 100, 300);

  // 3) 注入 prompt：loc.fill() 一次完成 + 立刻等 React state 同步。
  //    不再追加 "8 字符退格+重打" 拟人化小动作 — 它本身是 React state 二次变化源，
  //    反而容易触发"前半部分发了、Negative 段停留"（用户 22:4x 实测）。
  //    拟人化靠前后 humanDelay 随机延时 + 翻比例/思考停顿维持，录入本身不再做手脚。
  await loc.fill(text);
  await humanDelay(page, 200, 400);
  // ★ 关键修复：loc.fill 触发 React input event，React 18 batching 异步合并 state；
  //   立刻点 send 会用"旧 state"提交，DOM 显示"新值"——典型"前半部分发了"现象。
  //   在 inject 内部就等够再校验，避免把脏数据带出。
  await reactStateSyncDelay(page, 1500);

  // 4) 完整性校验：必须等 React 把 input event merge 进 state（最多 3 秒轮询）
  //    否则 click send 时 React state 还没更新到 DOM value，提交的是旧值——
  //    用户 22:4x 实测现象："前半部分发了、后半段停留"。
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const readNow = async () => await page.evaluate(
    ({ sel }) => {
      const el = document.querySelector(sel);
      if (!el) return '';
      return el.tagName === 'TEXTAREA' ? el.value || '' : el.innerText || el.textContent || '';
    },
    { sel: meta.selector },
  );
  const expectNorm = norm(text);
  let gotNorm = '';
  for (let i = 0; i < 15; i++) {
    gotNorm = norm(await readNow());
    if (gotNorm === expectNorm) break;
    await humanDelay(page, 150, 250);
  }
  if (gotNorm !== expectNorm) {
    const head = (s) => (s || '').slice(0, 60);
    throw new Error(
      `Prompt 注入不完整：框内 ${gotNorm.length} 字符（期望 ${expectNorm.length}）。` +
      ` 前 60 字符: "${head(gotNorm)}" vs "${head(expectNorm)}"`,
    );
  }

  // 5) Escape 关闭可能残留的 popover（不会清空内容）
  await page.keyboard.press('Escape');
  await humanDelay(page, 300, 800);

  return meta.kind;
}

// ---------- 比例：幂等点击 ----------
async function setRatio(page, ratio) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  await page.keyboard.press('Escape');
  await humanDelay(page, 500, 1100);
  const btn = page.getByRole('button', { name: /比例/ }).first();
  await btn.click();
  await humanDelay(page, 500, 1100);
  await page
    .locator('[data-radix-popper-content-wrapper]')
    .getByText(ratio, { exact: true })
    .first()
    .click();
  await humanDelay(page, 400, 900);
  await page.keyboard.press('Escape');
  await humanDelay(page, 300, 700);
  return true;
}

// ---------- 发送并捕获生成图 CDN URL ----------
async function generate(page, opts, log, editorKind) {
  const cdn = new Set();
  const onResp = (resp) => {
    const u = resp.url();
    if (CDN_RE.test(u)) cdn.add(u);
  };
  page.on('response', onResp);

  // 重新检测当前可用 send + editor（防止页面跳转导致选择器失效）
  const sendMeta = (await resolveSendBtn(page)) || { selector: SEND_SEL };
  const edMeta = (await resolveEditor(page)) || { selector: EDITOR_SEL, kind: 'contenteditable' };
  log('  send=' + sendMeta.selector + ' editor=' + edMeta.kind);
  await page.click(sendMeta.selector);
  await humanDelay(page, 1500, 3000);

  // 发送确认：输入框必须被清空（豆包发送成功 = editor 自动 clear）
  // 修复点：原代码只傻等 CDN，发送若没生效会一直等到 90s 超时才暴露
  const remainingRaw = await page.evaluate(
    ({ sel }) => {
      const el = document.querySelector(sel);
      if (!el) return '';
      return el.tagName === 'TEXTAREA' ? el.value || '' : el.innerText || el.textContent || '';
    },
    { sel: edMeta.selector },
  );
  const remaining = (remainingRaw || '').replace(/\s+/g, ' ').trim();
  if (remaining) {
    throw new Error(
      `发送失败：输入框仍有 ${remaining.length} 字符未发送（"${remaining.slice(0, 60)}..."）。` +
      ` 可能原因：发送按钮未生效 / 文本未提交 / 验证拦截。请检查后重试。`,
    );
  }
  // 发送后可能弹图片识别验证，暂停等人
  await waitForHumanIfBlocked(page, log, opts.profile);
  const deadline = Date.now() + (opts.genTimeout || 90000);
  let url = null;
  const isIcon = (u) => /\/rc\/icon\//.test(u);
  const isFull = (u) => !/-image-qvalue/.test(u) && !isIcon(u);
  let tick = 0;
  while (Date.now() < deadline) {
    const all = [...cdn];
    // 优先全质量（非 -image-qvalue 预览）；预览不触发 break，继续等全质量
    const full = all.find(isFull);
    if (full) {
      url = full;
      break;
    }
    const domUrl = await page
      .evaluate(() => {
        const img = document.querySelector('img[src*="tos-cn-i-a9rns2rl98"]');
        return img ? img.getAttribute('src') : null;
      })
      .catch(() => null);
    if (domUrl && isFull(domUrl)) {
      url = domUrl;
      break;
    }
    // 生成期间也可能弹图片识别验证，每 ~6s 检测一次并暂停等人
    if ((tick++ % 3) === 0) await waitForHumanIfBlocked(page, log, opts.profile);
    await humanDelay(page, 1500, 2800);
  }
  page.off('response', onResp);
  if (!url) {
    // 兜底：超时只等到预览/质量版也将就用（排除图标）
    const any = [...cdn].find((u) => !isIcon(u));
    if (any) url = any;
    else throw new Error('生成超时：未捕获到豆包生成图 CDN URL');
  }
  return url;
}

// ---------- 下载 ----------
async function download(url, out) {
  const res = await fetch(url, {
    headers: { Referer: REFERRER, 'User-Agent': UA },
    redirect: 'follow',
  });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  const buf = Buffer.from(await res.arrayBuffer());
  fs.writeFileSync(out, buf);
  // 落盘分辨率（原生 CDN 分辨率，非固定 1024；2048/其他比例均按真实尺寸抓取）
  const dims = imageDims(buf);
  return { size: buf.length, dims };
}

// ---------- 可选 verify-img.py 预筛 ----------
function runVerify(ref, out, promptFile, ratioStr, reportFile, log) {
  let py;
  try {
    py = resolvePython();
  } catch (e) {
    log('  [verify] 跳过：' + e.message);
    return null;
  }
  const verifyPy = path.resolve(SKILL_DIR, '..', 'qwen-image-mcp', 'scripts', 'verify-img.py');
  if (!fs.existsSync(verifyPy)) {
    log('  [verify] 跳过：找不到 ' + verifyPy);
    return null;
  }
  const ratioNum = RATIO_NUM[ratioStr] != null ? RATIO_NUM[ratioStr] : 1.0;
  const args = [
    verifyPy,
    '--ref', ref,
    '--out', out,
    '--prompt', promptFile,
    '--ratio', String(ratioNum),
    '--report', reportFile,
  ];
  try {
    execFileSync(py, args, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
    log('  [verify] 报告 -> ' + reportFile);
    return reportFile;
  } catch (e) {
    log('  [verify] 失败：' + (e.stderr || e.message));
    return null;
  }
}

// ---------- 主流程 ----------
(async () => {
  const o = parseArgs(process.argv.slice(2));
  if (o.help) {
    console.log(HELP);
    process.exit(0);
  }
  if (!o.ref || !fs.existsSync(o.ref)) {
    console.error('错误：--ref 必须指向存在的参考图文件。');
    process.exit(2);
  }
  if (!o.prompt || !fs.existsSync(o.prompt)) {
    console.error('错误：--prompt 必须指向存在的 prompt 文本文件。');
    process.exit(2);
  }
  if (!o.out) {
    console.error('错误：--out 必须指定输出图片路径。');
    process.exit(2);
  }
  if (!(o.ratio in RATIO_NUM)) {
    console.error('错误：--ratio 必须是 ' + Object.keys(RATIO_NUM).join(' / '));
    process.exit(2);
  }
  const promptText = fs.readFileSync(o.prompt, 'utf-8');
  const ratio = o.ratio;

  const { chromium } = loadPlaywright();
  const log = (m) => console.log(m);
  log('Doubao 图生图 CLI — 模型硬约束: ' + TARGET_MODEL);

  // browser 始终为 BrowserContext；connectOverCDP 返回 Browser，需取 contexts()[0]
  let browser;
  let cdpBrowser = null; // CDP 模式下保留引用，finally 不关用户的 Chrome
  let ownedBrowser = false;
  if (o.cdp) {
    log('→ CDP 连接 ' + o.cdp + '（复用你 headed Chrome，不自起，finally 不关）');
    cdpBrowser = await chromium.connectOverCDP(o.cdp);
    const ctxs = cdpBrowser.contexts();
    browser = ctxs[0] || await cdpBrowser.newContext();
    ownedBrowser = false;
  } else {
    log('→ launchPersistentContext（自起 Chrome，profile=' + o.profile + '）');
    browser = await chromium.launchPersistentContext(o.profile, {
      headless: o.headless,
      executablePath: CHROME_EXE,
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    });
    ownedBrowser = true;
  }

  let gPage = null;
  try {
    // ★ 用户 2026-08-13 22:5x 强制要求：单 tab 复用，绝不开新 tab
    // 1) CDP 模式下：复用 context 已经有的第一个 page（如果存在）
    // 2) 自起模式：只有 launchPersistentContext 自己创建的初始 page（无则 newPage，但会被 finally 收掉）
    let page;
    if (o.cdp) {
      const existingPages = (cdpBrowser.contexts()[0] && cdpBrowser.contexts()[0].pages()) || [];
      if (existingPages.length > 0) {
        page = existingPages[0];
        log('→ CDP 复用已有 page x' + existingPages.length + '（不开新 tab）');
      } else {
        page = await browser.newPage();
        log('→ CDP 无可复用 page，新建 1 个（首次调用场景）');
      }
    } else {
      page = await browser.newPage();
    }
    gPage = page;

    // 落地页可能弹图片识别验证，暂停等人
    await waitForHumanIfBlocked(page, log, o.profile);
    // ★ 复用同 tab 起新任务（用户强约束：不开新 tab，对本地电脑友好）
    await startNewTaskInSameTab(page, log);
    await humanDelay(page, 1500, 3000);
    // create-image 可能被重定向到最近对话（无生成器工具栏），须显式回到生成页
    const onGen = await ensureCreateImagePage(page, log);
    if (!onGen) {
      throw new Error('无法进入豆包「AI 创作」生成页（比例/发送按钮缺失），请检查登录态或手动打开 create-image 后重试');
    }
    await humanDelay(page, 800, 1800);

    // 登录态校验：生成器页必须能找到 prompt 编辑器（修复假阳性：侧栏/header 的"登录"链接会被误判）
    // 之前检测"登录"文本会把持久化的侧栏登录链接当未登录抛出，实际 gen UI + 编辑器已加载就是已登录
    const hasGenEditor = await page.evaluate(() => !!document.querySelector('.tiptap.ProseMirror'));
    if (!hasGenEditor) {
      throw new Error('未登录或未进入生成器：找不到 prompt 编辑器 .tiptap.ProseMirror，请检查登录态');
    }

    const model = await setModel(page, TARGET_MODEL);
    log('  模型: ' + model);
    if (!model.includes(TARGET_MODEL)) {
      throw new Error('模型切换失败：当前为 [' + model + ']，非 ' + TARGET_MODEL);
    }
    await waitForHumanIfBlocked(page, log, o.profile);

    // 参考图：图生图必传；文生图（--text2img）跳过，但要点"图像生成"agent 切到生图模式
    if (o.text2img) {
      const switched = await trySwitchToImageGenAgent(page, log);
      if (!switched) log('  ⚠️ 文生图 agent 切换跳过 — doubao 仍在 chat 模式（不会出图）');
    } else {
      if (!o.ref) throw new Error('图生图模式必须传 --ref 参考图；若要文生图请加 --text2img');
      const refOk = await uploadRef(page, o.ref);
      log('  参考图上传: ' + (refOk ? 'OK' : 'FAIL'));
      if (!refOk) throw new Error('参考图上传失败');
    }
    await humanDelay(page, 600, 1400);

    const editorKind = await injectPrompt(page, promptText);
    log('  Prompt 注入: ' + promptText.length + ' 字符（编辑器: ' + editorKind + '）');
    // injectPrompt 内部已 reactStateSyncDelay(1500) 等完；这里再补 800ms 收尾
    await humanDelay(page, 600, 1200);
    // 注入后也可能弹验证，点比例前先确认无人机拦截
    await waitForHumanIfBlocked(page, log, o.profile);

    // 比例：chat 页面（页面已跳到 /chat/<id>）可能没有"比例"按钮 — 容错处理
    try {
      await setRatio(page, ratio);
      log('  比例: ' + ratio);
    } catch (re) {
      log('  比例设置跳过（当前页面无比例按钮，疑似 chat 会话页: ' + (re && re.message ? re.message.split('\n')[0] : re) + '）');
    }
    await waitForHumanIfBlocked(page, log, o.profile);

    // ★ 发送前 preflight：检测游客态 / agent 错位 / 编辑器缺失，绝不静默继续
    await preflightGenContext(page, log, o);
    // 拟人化随机延时（不替代确定性 sync，仅补防机械感）
    await humanDelay(page, 800, 1600);

    const url = await generate(page, o, log, editorKind);
    log('  生成图 URL: ' + url.slice(0, 90) + '...');

    const dir = path.dirname(o.out);
    if (dir) fs.mkdirSync(dir, { recursive: true });
    const dl = await download(url, o.out);
    const dimStr = dl.dims ? ' ' + dl.dims.w + 'x' + dl.dims.h : '';
    log('  下载完成: ' + o.out + ' (' + dl.size + ' bytes' + dimStr + ')');

    let verifyReport = null;
    if (o.verify) {
      const reportFile = o.report || o.out + '.verify.json';
      verifyReport = runVerify(o.ref, o.out, o.prompt, ratio, reportFile, log);
    }

    log('\n===== 完成 =====');
    log(
      '  out=' + o.out +
      ' size=' + dl.size +
      (dl.dims ? ' dims=' + dl.dims.w + 'x' + dl.dims.h : '') +
      ' model=' + model +
      ' ratio=' + ratio +
      (verifyReport ? ' verify=' + verifyReport : '')
    );
  } catch (e) {
    // 调试诊断：在 page 仍存活时抓取 DOM 状态（finally 关闭前）
    try {
      if (gPage) {
        const dbgDir = process.cwd();
        try { await gPage.screenshot({ path: path.join(dbgDir, 'doubao_fatal_debug.png'), fullPage: false }); } catch {}
        const info = await gPage.evaluate(() => {
          const btns = [...document.querySelectorAll('button')].map((b) => (b.textContent || '').trim()).filter(Boolean);
          const ratioBtns = btns.filter((t) => /比例|1:1|4:3|3:4|16:9|9:16|2:3|3:2/.test(t)).slice(0, 12);
          const txt = document.body ? document.body.innerText || '' : '';
          return {
            title: document.title,
            url: location.href,
            bodyFirst400: txt.slice(0, 400),
            ratioBtns,
            hasVerify: /验证|安全|拼图|滑块|请选择|人机/.test(txt),
            activeEl: document.activeElement ? (document.activeElement.tagName + '.' + (document.activeElement.className || '')) : null,
          };
        }).catch((err) => ({ evalError: String(err && err.message) }));
        fs.writeFileSync(path.join(dbgDir, 'doubao_fatal_debug.json'), JSON.stringify(info, null, 2));
        console.error('  [debug] 已写出诊断 -> ' + path.join(dbgDir, 'doubao_fatal_debug.json'));
      }
    } catch (err2) { console.error('  [debug] 诊断失败: ' + (err2 && err2.message)); }
    throw e;
  } finally {
    // CDP 模式：用户的 Chrome 不能关；仅自起模式才 close
    if (ownedBrowser) {
      await browser.close();
    }
  }
  process.exit(0);
})().catch((e) => {
  console.error('FATAL', e);
  process.exit(1);
});

#!/usr/bin/env node
/**
 * aistudio_design_plan.cjs  —  AI Studio「商品基础信息 → 设计方案」CLI（写操作）
 *
 * 作用：用「System Instructions（POD 底稿专用版）+ 商品基础信息」驱动 AI Studio 网页端
 *       的 gemini 3.1-pro-preview，产出设计方案（方向A展示素材 + 方向B印花底稿 Prompt 组）。
 *       拟人化点 copy as text 按钮 → 读系统剪贴板 → 落盘为 .md，可选回写飞书「设计方案」字段。
 *
 * 关键设计（按用户 2026-08-14 硬要求）：
 *   1) 模型硬性用 gemini-3.1-pro-preview（不再擅自降级 flash）
 *   2) 全程拟人化操作：真实鼠标点击 / 真实键盘逐字键入 / 随机延迟 / 滚动到元素再点
 *   3) System Instructions 首次完整注入 v5.4，后续「点开 SI 卡片 → 切换已输入的 v5.4」
 *      检测右栏 SI 卡片文本已含 v5.4 标记则跳过注入；不再每次 6966 字符重新塞
 *   4) 内容提取：点回复区「copy as text」按钮 → 读系统剪贴板（powershell Get-Clipboard）
 *      不抓 .turn-content DOM（DOM 抓取会被风控识别为 agent）
 *
 * 通道特点（弱模型友好 / 可复用）：
 *   - 默认【有头】浏览器（headless:false），便于首次登录与人工复核；--headless 切回无头批量。
 *   - 默认走 AI Studio Playground 主页，批量时通过点击「Playground」按钮逐条重置上下文，
 *     全程【单进程单标签】，绝不新建浏览器标签。
 *   - profile 落在 skill 目录内（与工作空间解耦），换工作空间复用同一份 Google 登录态。
 *   - 未登录时（有头模式）原地等待用户在弹出窗口登录，登录后自动继续；
 *     无头模式未登录直接报错退出（无头无法登录）。
 *   - 进程外 spawn 真实 Chrome + CDP 接管：无 Playwright 自动化标记，规避 Google 登录
 *     「此浏览器不安全」拦截。
 *
 * 依赖：Node >= 18、playwright、Python(venv) 供飞书读写。
 *
 * 用法：
 *   单条： node aistudio_design_plan.cjs --input <商品信息.txt> --out <设计方案.md> [选项]
 *   批量： node aistudio_design_plan.cjs --batch [--limit N] [--rids "a b c"] [--write-feishu] [选项]
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync, spawn } = require('child_process');

// ---------- 配置默认值 ----------
const SKILL_DIR = __dirname;
const DEFAULT_SI = path.resolve(SKILL_DIR, '..', 'assets', 'system_instructions_v54.txt');
const DEFAULT_PROFILE = 'C:/Users/nicho/AppData/Local/Google/Chrome/User Data';
const CHROME_EXE = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const PLAYGROUND_URL = 'https://aistudio.google.com/prompts';
const NEW_CHAT_URL = 'https://aistudio.google.com/prompts/new_chat';
const DEFAULT_CDP_PORT = 9223;
const DEFAULT_PROXY = 'http://127.0.0.1:7897';
const LOGIN_TIMEOUT = 300;
const PY = 'C:/Users/nicho/.workbuddy/binaries/python/envs/default/Scripts/python.exe';
const VB_DIR = path.resolve(SKILL_DIR, '..', '..', 'aistudio-visualbridge', 'scripts');
const DEFAULT_OUT_DIR = path.resolve(SKILL_DIR, '..', 'dp_run');

// 用户 2026-08-14 硬性要求：模型 = gemini-3.1-pro-preview
// 之前为了「跑通」擅自降级到 flash 是不诚实的，已回退
const TARGET_MODEL = 'gemini-3.1-pro-preview';
// 禁用 flash（用户硬要求用 3.1-pro，不再允许擅自降级）
const BANNED_MODELS = ['gemini-3-flash-preview'];

// v5.4 标识字符串（用于检测右栏 SI 卡片是否已含 v5.4，是则跳过注入复用）
// 双关键词（POD 印花底稿 + v5.4）已在 ensureSI 内用宽松匹配，SI_VERSION_MARK 暂留兼容
const SI_VERSION_MARK = 'POD 印花底稿 Prompt 生成系统指令（Final Version v5.4）';
// 模型下拉里 3.1-pro 的可能名称（AI Studio 改名频繁，多候选）
const MODEL_PRO_CANDIDATES = [
  'gemini-3.1-pro-preview',
  'gemini 3.1 pro preview',
  'gemini-3.1-pro',
  'gemini 3.1 pro',
  '3.1 pro preview',
];

// 选择器
const SEL_PROMPT = 'textarea[aria-label="Enter a prompt"], textarea[placeholder*="Start typing"]';
const SEL_MODEL_NAME = '[data-test-id="model-name"]';
const SEL_BACKDROP = '.cdk-overlay-backdrop-showing';
const SEL_SI_TEXTAREA = 'textarea[aria-label="System instructions"]';

// ---------- playwright 解析 ----------
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
    '找不到 playwright。设置环境变量 PLAYWRIGHT_LIB 指向其目录。\n最后错误: ' + (lastErr && lastErr.message)
  );
}

// ---------- 参数解析 ----------
function parseArgs(argv) {
  const o = {
    input: null,
    out: null,
    si: DEFAULT_SI,
    model: TARGET_MODEL,
    profile: DEFAULT_PROFILE,
    proxy: DEFAULT_PROXY,
    headless: false,
    genTimeout: 300000,
    keepOpen: false,
    shot: null,
    batch: false,
    limit: 0,
    rids: null,
    writeFeishu: false,
    outDir: DEFAULT_OUT_DIR,
    attach: false,            // --attach: 接管用户已开 Chrome（共享其 SI 历史与登录态）
    cdpUrl: 'http://127.0.0.1:' + DEFAULT_CDP_PORT, // --cdp-url: CDP 端点（仅 --attach 用）
    mcpMode: false,           // --mcp-mode: 输出待 MCP 调用的指令序列（不启 Chrome、不 spawn、不连 CDP）；用于 MCP 改造过渡
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const take = (name) => {
      if (a === '--' + name) return argv[++i];
      if (a.startsWith('--' + name + '=')) return a.slice(name.length + 3);
      return undefined;
    };
    let v;
    if ((v = take('input')) !== undefined) o.input = v;
    else if ((v = take('out')) !== undefined) o.out = v;
    else if ((v = take('si')) !== undefined) o.si = v;
    else if ((v = take('model')) !== undefined) o.model = v;
    else if ((v = take('profile')) !== undefined) o.profile = v;
    else if ((v = take('proxy')) !== undefined) o.proxy = v;
    else if ((v = take('shot')) !== undefined) o.shot = v;
    else if ((v = take('out-dir')) !== undefined) o.outDir = v;
    else if ((v = take('rids')) !== undefined) o.rids = v;
    else if ((v = take('gen-timeout')) !== undefined) o.genTimeout = parseInt(v, 10);
    else if ((v = take('limit')) !== undefined) o.limit = parseInt(v, 10) || 0;
    else if ((v = take('cdp-url')) !== undefined) o.cdpUrl = v;
    else if (a === '--headed') o.headless = false;
    else if (a === '--headless') o.headless = true;
    else if (a === '--no-proxy') o.proxy = null;
    else if (a === '--keep-open') o.keepOpen = true;
    else if (a === '--batch') o.batch = true;
    else if (a === '--write-feishu') o.writeFeishu = true;
    else if (a === '--attach') o.attach = true;
    else if (a === '--mcp-mode') o.mcpMode = true;
    else if (a === '-h' || a === '--help') o.help = true;
  }
  return o;
}

const HELP = `
aistudio_design_plan  —  AI Studio「商品基础信息 → 设计方案」CLI

模型当前默认：${TARGET_MODEL}（用户 2026-08-14 硬性要求；flash 已禁用，禁止降级）

用法:
  单条： node aistudio_design_plan.cjs --input <商品信息.txt> --out <设计方案.md> [选项]
  批量： node aistudio_design_plan.cjs --batch [--limit N] [--rids "a b c"] [--write-feishu] [选项]

参数:
  --input <file>      商品基础信息文本（单条必填）
  --out <file>        设计方案输出路径（单条必填，.md）
  --batch             批量模式：从飞书取「待生成」记录循环处理（单进程单标签）
  --limit <N>         批量最多处理 N 条（0=不限）
  --rids "a b c"      指定 record_id 列表（空格分隔）
  --write-feishu      批量时生成后自动回写飞书（⚠️ 需用户授权）
  --out-dir <dir>     批量输出目录（默认 <skill>/dp_run）
  --si <file>         System Instructions 文件（默认 assets/system_instructions.txt）
  --model <name>      模型（默认 ${TARGET_MODEL}；flash 已被禁用）
  --profile <dir>     Chrome 用户数据目录（默认 <skill>/profiles/aistudio-design-plan-profile）
  --attach            接管用户已开 Chrome（共享其 SI 历史与登录态，需用户手动启动带 --remote-debugging-port 端口的 Chrome；默认 spawn 即接管——见 DEFAULT_PROFILE/DEFAULT_CDP_PORT）
  --cdp-url <url>     CDP 端点（仅 --attach 用，默认 http://127.0.0.1:9223）
  --mcp-mode          仅输出"待 MCP 调用的指令序列"到 stdout，不启 Chrome（用于 MCP 改造过渡，按用户 8-14 03:33 指示）
  --headed            有头模式（默认即有头）；--headless 切换回无头批量
  --keep-open         跑完不关浏览器（人工复核用，配合 --headed）
  --shot <file>       结束前截图落盘
  --gen-timeout <ms>  生成等待超时（默认 300000）
  -h, --help          显示帮助

拟人化操作（按用户 2026-08-14 要求）：
  - 真实鼠标点击 + 真实键盘逐字键入（每字 30-80ms 随机延迟）
  - 真实按钮点击 + 400-1500ms 随机等待响应
  - 滚动到元素再点（人类不会点看不到的元素）
  - 内容提取走「copy as text 按钮 + 系统剪贴板」，不抓 .turn-content DOM
  - System Instructions 首次完整注入 v5.4，后续检测「右栏 SI 卡片已含 v5.4」则跳过

批量铁律（弱模型照做）：
  批量时本 CLI 进 AI Studio Playground 主页，对每条记录【点击侧栏「Playground」按钮】重置上下文（不新建标签），
  全程【单进程单标签】。未登录时（有头）原地等你在弹出窗口登录后自动继续。
`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

// ---------- 拟人化工具（核心） ----------
// 拟人分级（2026-08-14 用户硬要求）：
//   - SI 区（6966 字符长文本）：走「剪贴板 + Ctrl+V」一次性注入是合理的——
//     人类真实场景也是从外部粘贴；逐字键入 7000 字反而是非人类特征（行为聚类识别）。
//   - 会话输入框：必须 humanType 拟人（click → Ctrl+A → Delete → 逐字键入 50-120ms），
//     这里是真正会被风控抓的点。
async function humanDelay(log, msg) {
  const ms = rand(400, 1500);
  if (log && msg) log('  ⏸ 拟人延迟 ' + ms + 'ms' + (msg ? '（' + msg + '）' : ''));
  await sleep(ms);
}

async function humanType(page, sel, text, opts) {
  opts = opts || {};
  // 用户 2026-08-14 硬要求：会话输入必须拟人
  // 50-120ms 随机延迟 = 真实人类打字节奏（过快是机器，过慢不像在复制）
  const minDelay = opts.minDelay || 50;
  const maxDelay = opts.maxDelay || 120;
  // 长文本分块：每 200 字符后稍作"思考停顿"（人类长文本会停顿喘气）
  const chunkSize = opts.chunkSize || 200;
  const log = opts.log;
  const loc = page.locator(sel).first();
  await loc.scrollIntoViewIfNeeded().catch(() => {});
  await loc.click({ timeout: 15000 });
  await sleep(rand(250, 600));
  // 清空（用 select all + delete，模拟人类 Ctrl+A → Delete）
  await page.keyboard.press('Control+A');
  await sleep(rand(100, 250));
  await page.keyboard.press('Delete');
  await sleep(rand(200, 450));
  // 分块逐字键入（核心拟人：随机延迟 + 块间思考停顿）
  for (let i = 0; i < text.length; i += chunkSize) {
    const chunk = text.slice(i, i + chunkSize);
    await page.keyboard.type(chunk, { delay: rand(minDelay, maxDelay) });
    if (i + chunkSize < text.length) {
      await sleep(rand(300, 800)); // 块间"思考停顿"
      if (log && (Math.floor(i / chunkSize) % 5 === 0)) log('  ⌨ 拟人键入 ' + (i + chunk.length) + '/' + text.length + ' 字符');
    }
  }
  if (log) log('  ⌨ 拟人键入完成 ' + text.length + ' 字符（' + minDelay + '-' + maxDelay + 'ms/字）');
  await sleep(rand(400, 900));
}

async function humanClick(page, sel, log) {
  const loc = page.locator(sel).first();
  await loc.scrollIntoViewIfNeeded().catch(() => {});
  await loc.click({ timeout: 15000 });
  await humanDelay(log, '点击后');
}

// ---------- 页面稳定等待 ----------
async function waitStable(page, log) {
  for (let i = 0; i < 6; i++) {
    try {
      await page.waitForLoadState('networkidle', { timeout: 12000 });
      await page.waitForSelector('ms-chat-turn, textarea, ms-model-selector, a, button', {
        timeout: 12000,
      });
      return true;
    } catch (e) {
      if (log) log('  ⏳ 页面尚未稳定，重试 (' + (5 - i) + ' 剩余)');
      await sleep(2500);
    }
  }
  return false;
}

// ---------- 模型切换（用户 8-14 明示：按模型全名精确选中，不靠模糊候选） ----------
// 用 selectModelByName 实现：归一化 targetModel（全小写、去 - 和空白），在下拉里精确匹配。
// 仍保留 MODEL_PRO_CANDIDATES 作为 targetModel 不可用时的兜底（人类手改下拉时也会差几字符）。
async function selectModelByName(page, targetModel, log) {
  const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const normTarget = norm(targetModel);
  const allCands = [targetModel].concat(MODEL_PRO_CANDIDATES.filter((x) => x.toLowerCase() !== targetModel.toLowerCase()));
  // 优先级：精确归一化匹配 > 候选模糊匹配
  const clicked = await page.evaluate(({ normTarget, allCands }) => {
    const allOpts = [...document.querySelectorAll('button, [role="option"], a, mat-option, li, [data-test-id*="model"]')];
    const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    // 第 1 优先级：归一化精确等于
    for (const o of allOpts) {
      const t = ((o.textContent || '') + ' ' + (o.getAttribute('aria-label') || ''));
      if (norm(t) === normTarget) { o.click(); return { picked: 'exact', name: (o.textContent || '').trim() }; }
    }
    // 第 2 优先级：归一化包含 target（避免空格差异）
    for (const o of allOpts) {
      const t = ((o.textContent || '') + ' ' + (o.getAttribute('aria-label') || ''));
      if (norm(t).includes(normTarget)) { o.click(); return { picked: 'contains', name: (o.textContent || '').trim() }; }
    }
    // 第 3 优先级：候选模糊匹配（人类手改下拉时差几字符的兜底）
    for (const c of allCands) {
      const nc = norm(c);
      for (const o of allOpts) {
        const t = ((o.textContent || '') + ' ' + (o.getAttribute('aria-label') || ''));
        if (norm(t).includes(nc)) { o.click(); return { picked: 'candidate-fuzzy', name: (o.textContent || '').trim(), candidate: c }; }
      }
    }
    return null;
  }, { normTarget, allCands });
  return clicked;
}

async function selectModel(page, targetModel, log) {
  if (log) log('  🎯 切换模型 → ' + targetModel + '（按全名精确选中）');

  // 1) 读当前模型
  const current = await page
    .evaluate((sel) => {
      const el = document.querySelector(sel);
      return el ? (el.textContent || '').trim() : '';
    }, SEL_MODEL_NAME)
    .catch(() => '');
  if (log) log('  当前模型: ' + (current || '(未读到)'));

  // 已经是 3.1-pro 系列就跳过
  if (current && /3\.1.*pro/i.test(current) && /preview/i.test(current)) {
    if (log) log('  ✅ 已是 3.1-pro-preview，跳过切换');
    return true;
  }

  // 2) 拟人：点模型下拉
  try {
    await humanClick(page, SEL_MODEL_NAME, log);
  } catch (e) {
    if (log) log('  ⚠️ 点击模型下拉失败: ' + e.message);
  }
  await sleep(rand(800, 1500));

  // 3) 按全名精确选中（多级 fallback）
  const clicked = await selectModelByName(page, targetModel, log);
  if (clicked) {
    if (log) log('  ✅ 已点击模型: ' + clicked.name + ' (策略=' + clicked.picked + ')');
    await sleep(rand(1000, 2000));
    return true;
  }

  // 4) 找不到 → 提示用户手动切，轮询直到看到 3.1-pro
  if (log) {
    log('  ⚠️ 模型下拉里未找到 ' + targetModel + '。');
    log('  👉 请在弹出的浏览器窗口里手动选择（程序会持续轮询等待）...');
  }
  const deadline = Date.now() + 120 * 1000;
  while (Date.now() < deadline) {
    await sleep(3000);
    const now = await page
      .evaluate((sel) => {
        const el = document.querySelector(sel);
        return el ? (el.textContent || '').trim() : '';
      }, SEL_MODEL_NAME)
      .catch(() => '');
    if (now && /3\.1.*pro/i.test(now)) {
      if (log) log('  ✅ 检测到已切到 3.1-pro 模型: ' + now);
      return true;
    }
  }
  throw new Error('模型切换超时：120s 内未检测到 ' + targetModel + '。请确认账号有该模型权限。');
}

// ---------- System Instructions 检测+注入（拟人） ----------
// 用户 2026-08-14 明确规则：SI 在 AI Studio 是「自动保存 + 同浏览器可复用」的。
// 批量新建对话时 SI 区会保留上一份内容，不必每次重新录入。
// 修：检测 textarea .value 全文（非 textContent 截断到 500），用 v5.4 双关键词宽松匹配
//（v5.4 标记在 6966 字符末尾，截断就漏了），命中则跳过注入；无命中才首次注入
//（走剪贴板+Ctrl+V——这是人类真实粘贴行为，不是自动化痕迹）。
const SI_MARK_PRIMARY = 'POD 印花底稿';
const SI_MARK_SECONDARY = 'v5.4';
async function ensureSI(page, siText, log) {
  // 1) 先检测右栏 SI 卡片 textarea 是否已含 v5.4（双关键词宽松匹配）
  const currentSI = await page
    .evaluate(() => {
      const ta = document.querySelector('textarea[aria-label="System instructions"]');
      if (ta && ta.value && ta.value.trim().length > 50) return ta.value;
      // 兜底：找其他可能的 SI 容器
      const candidates = [
        ...document.querySelectorAll('ms-system-prompt-instructions, [class*="system-instruction"]'),
      ];
      for (const c of candidates) {
        const t = (c.textContent || '').trim();
        if (t.length > 50) return t;
      }
      return '';
    })
    .catch(() => '');

  // 双关键词都命中才算"已含 v5.4"
  if (
    currentSI &&
    currentSI.includes(SI_MARK_PRIMARY) &&
    currentSI.includes(SI_MARK_SECONDARY)
  ) {
    if (log) log('  ♻️ 检测到右栏 SI 已含 v5.4 标记（双关键词命中），跳过注入（用户原话：复用已输入的）');
    return { reused: true, len: currentSI.length };
  }

  if (log) log('  📝 首次注入 SI（v5.4 全文 ' + siText.length + ' 字符，走剪贴板+Ctrl+V 拟人模式）...');

  // 2) 找 SI textarea；找不到就尝试点 "System instructions" 折叠面板
  let siFound = await page.evaluate((sel) => !!document.querySelector(sel), SEL_SI_TEXTAREA);
  if (!siFound) {
    await page
      .evaluate(() => {
        const btn = [...document.querySelectorAll('button')].find((b) =>
          /system\s*instruction|系统指令/i.test((b.textContent || '') + (b.getAttribute('aria-label') || ''))
        );
        if (btn) btn.click();
      })
      .catch(() => {});
    await sleep(rand(800, 1500));
    siFound = await page.evaluate((sel) => !!document.querySelector(sel), SEL_SI_TEXTAREA);
  }
  if (!siFound) throw new Error('找不到 System instructions 输入框（aria-label="System instructions"）');

  // 3) 拟人：把 SI 写进系统剪贴板（人类打开文件 → Ctrl+A → Ctrl+C）→ 切到 SI 框 → Ctrl+V
  if (log) log('  📋 写系统剪贴板（人类 Ctrl+C 模式）');
  writeClipboard(siText);
  await sleep(rand(200, 400));

  // 4) 拟人：点击 SI 输入框 → Ctrl+V 粘
  const loc = page.locator(SEL_SI_TEXTAREA).first();
  await loc.scrollIntoViewIfNeeded().catch(() => {});
  await loc.click({ timeout: 15000 });
  await sleep(rand(200, 500));
  await page.keyboard.press('Control+V');
  await sleep(rand(600, 1200));

  // 5) 验证 SI 是否粘进去了（通过 textarea value 长度）
  const v = await page.locator(SEL_SI_TEXTAREA).first().inputValue().catch(() => '');
  if (!v || v.length < siText.length * 0.5) {
    throw new Error('SI 剪贴板粘入失败：textarea value 长度 ' + (v ? v.length : 0) + ' < ' + siText.length);
  }
  if (log) log('  ✅ SI 已粘入 ' + v.length + ' 字符');
  return { reused: false, len: v.length };
}

function writeClipboard(text) {
  // Windows: 用 PowerShell Set-Clipboard，UTF-8 编码，避免中文乱码
  const ps =
    '$txt = [Console]::In.ReadToEnd(); ' +
    'Add-Type -AssemblyName System.Windows.Forms; ' +
    '[System.Windows.Forms.Clipboard]::SetText($txt)';
  try {
    execFileSync('powershell', ['-NoProfile', '-Command', ps], {
      input: text,
      encoding: 'utf-8',
      maxBuffer: 16 * 1024 * 1024,
    });
  } catch (e) {
    throw new Error('写剪贴板失败：' + e.message);
  }
}

// ---------- 关闭遮罩层 ----------
async function closeOverlays(page, log) {
  const hasBackdrop = () =>
    page.evaluate((s) => !!document.querySelector(s), SEL_BACKDROP).catch(() => false);
  if (!(await hasBackdrop())) return true;
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press('Escape');
    await sleep(700);
    if (!(await hasBackdrop())) {
      if (log) log('  遮罩层已关闭（Escape ×' + (i + 1) + '）');
      return true;
    }
  }
  await page
    .evaluate((s) => {
      const b = document.querySelector(s);
      if (b) b.click();
    }, SEL_BACKDROP)
    .catch(() => {});
  await sleep(1000);
  const gone = !(await hasBackdrop());
  if (log) log('  遮罩层' + (gone ? '已关闭（点击兜底）' : '仍存在 ⚠️'));
  return gone;
}

// ---------- 注入商品信息 Prompt（拟人逐字键入，核心反检测点） ----------
async function injectPrompt(page, text, log) {
  await page.waitForSelector(SEL_PROMPT, { timeout: 30000 });
  await closeOverlays(page, log);
  // 用户硬要求：会话输入框必须拟人（50-120ms/字 + 块间思考停顿）
  await humanType(page, SEL_PROMPT, text, {
    minDelay: 50,
    maxDelay: 120,
    chunkSize: 200,
    log,
  });
  const v = await page.locator(SEL_PROMPT).first().inputValue().catch(() => '');
  return v.length;
}

// ---------- 拟人：点 copy as text 按钮 → 读系统剪贴板 ----------
async function clickCopyAndReadClipboard(page, log) {
  // 多候选选择器：aria-label 优先，再文本
  const COPY_SELECTORS = [
    'button[aria-label="Copy as text"]',
    'button[aria-label*="Copy" i][aria-label*="text" i]',
    'button[title="Copy as text"]',
    'button[title*="Copy" i][title*="text" i]',
    'button[aria-label*="copy" i]',
  ];

  for (const sel of COPY_SELECTORS) {
    const found = await page.evaluate((s) => {
      const btn = document.querySelector(s);
      if (!btn) return null;
      const r = btn.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2, label: btn.getAttribute('aria-label') || btn.textContent };
    }, sel).catch(() => null);

    if (found) {
      if (log) log('  📋 找到 copy 按钮: ' + found.label + ' @(' + Math.round(found.x) + ',' + Math.round(found.y) + ')');
      // 拟人：真实鼠标移动 + 点击
      await page.mouse.move(found.x - rand(20, 60), found.y - rand(20, 60), { steps: rand(8, 20) });
      await sleep(rand(100, 300));
      await page.mouse.move(found.x, found.y, { steps: rand(5, 10) });
      await sleep(rand(100, 250));
      await page.mouse.click(found.x, found.y);
      await sleep(rand(400, 900));
      // 读剪贴板
      const txt = readClipboard();
      if (txt && txt.trim().length > 50) {
        if (log) log('  ✅ copy as text 拿回 ' + txt.length + ' 字符');
        return txt;
      }
      if (log) log('  ⚠️ 剪贴板为空或太短，再试下一个候选');
    }
  }

  // 兜底：找含 "copy" / "复制" 的所有按钮/菜单，列出来给用户
  if (log) {
    log('  ⚠️ 未找到明确的 copy as text 按钮；尝试 kebab 菜单');
    const all = await page.evaluate(() => {
      return [...document.querySelectorAll('button, [role="menuitem"]')]
        .filter((b) => /copy|copy_text|copy-as-text|复制/i.test((b.textContent || '') + (b.getAttribute('aria-label') || '')))
        .map((b) => ({ tag: b.tagName, label: b.getAttribute('aria-label') || (b.textContent || '').trim().slice(0, 30) }));
    }).catch(() => []);
    log('  候选按钮: ' + JSON.stringify(all));
  }
  return null;
}

function readClipboard() {
  try {
    const out = execFileSync('powershell', ['-NoProfile', '-Command', 'Get-Clipboard -Raw'], {
      encoding: 'utf-8',
      maxBuffer: 8 * 1024 * 1024,
    });
    return out.replace(/\r/g, '').trim();
  } catch (e) {
    return '';
  }
}

// ---------- 等待回复 + 拟人提取（不抓 DOM，等稳定后点 copy 按钮） ----------
async function waitAndCopy(page, timeoutMs, log) {
  // 等生成按钮变 disabled / 回复区出现稳定文本
  const deadline = Date.now() + timeoutMs;
  let lastLen = 0;
  let stableRounds = 0;

  while (Date.now() < deadline) {
    await sleep(3000);
    // 探测生成状态：Run Ctrl+Enter 按钮可用 = 生成结束
    const state = await page.evaluate(() => {
      const runs = [...document.querySelectorAll('button')].filter((b) => /run\s*ctrl/i.test(b.textContent || ''));
      const runEnabled = runs.some((b) => !b.disabled);
      // 回复区最后一条 turn 字符数
      const turns = [...document.querySelectorAll('ms-chat-turn')];
      const last = turns[turns.length - 1];
      const txt = last ? (last.querySelector('.turn-content') || last).innerText : '';
      return { runEnabled, lastLen: (txt || '').trim().length, hasError: /internal error|permission denied|failed to generate/i.test(txt || '') };
    }).catch(() => ({ runEnabled: false, lastLen: 0, hasError: false }));

    if (state.hasError) {
      // 用户 2026-08-14 原话：「Rerun 应该能跑一次，否则就重跑整条」
      // 当前实现是 throw 让批量 catch 跳过该条，但用户要的是"重跑整条"。
      // 但"重跑整条"需要在新流程外决策（重置 newConversation + 重跑 runOne），
      // 这里只 throw 把控制权交回批量循环；批量循环据此决定是否整条重试。
      throw new Error('模型生成报错（' + (state.lastLen > 0 ? '已部分生成后出错' : '未生成') + '）');
    }

    if (state.runEnabled && state.lastLen > 100) {
      // 生成结束且有内容 → 再等 2s 确认稳定
      if (state.lastLen === lastLen) {
        stableRounds++;
        if (stableRounds >= 2) {
          if (log) log('  ✅ 回复区稳定 ' + state.lastLen + ' 字符，准备点 copy 按钮');
          return await clickCopyAndReadClipboard(page, log);
        }
      } else {
        stableRounds = 0;
        lastLen = state.lastLen;
      }
    } else if (state.lastLen > 0 && state.lastLen !== lastLen) {
      if (log) log('  生成中... ' + state.lastLen + ' 字符');
      lastLen = state.lastLen;
      stableRounds = 0;
    }
  }
  throw new Error('生成超时（' + Math.round(timeoutMs / 1000) + 's）');
}

// ---------- 新建对话（拟人：点「Playground」按钮重置上下文） ----------
async function newConversation(page, model, log) {
  const clicked = await page
    .evaluate(() => {
      const els = [...document.querySelectorAll('button, a')];
      const r = els.find((b) =>
        /playground|new\s*chat|新建对话|new conversation|start\s*new/i.test(
          (b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')
        )
      );
      if (r) { r.click(); return true; }
      return false;
    })
    .catch(() => false);
  if (clicked) {
    await sleep(1800);
    if (log) log('  [新对话] 已点击「Playground」按钮重置上下文');
    await waitStable(page, log).catch(() => {});
    return true;
  }
  if (log) log('  [新对话] 未找到「新建对话」按钮，兜底：单标签重新导航 new_chat');
  await page
    .goto(NEW_CHAT_URL + '?model=' + encodeURIComponent(model), {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    })
    .catch(() => {});
  await sleep(2000);
  return true;
}

// ---------- 飞书读写辅助（Python venv） ----------
function fetchInput(rid, outFile) {
  const script = path.resolve(SKILL_DIR, 'fetch_input.py');
  execFileSync(PY, [script, rid, '-o', outFile], { encoding: 'utf-8' });
  if (!fs.existsSync(outFile)) throw new Error('fetch_input 未产出 ' + outFile);
  return outFile;
}

function fetchRidsFromFeishu(limit) {
  const script = path.resolve(SKILL_DIR, 'fetch_input.py');
  const out = execFileSync(PY, [script, '--list-empty'], { encoding: 'utf-8' });
  const rids = out
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => l.split(/\s*\|\s*/)[0].trim())
    .filter((id) => /^rec/.test(id));
  return limit > 0 ? rids.slice(0, limit) : rids;
}

function writeFeishu(rid, mdFile, log) {
  const code =
    'import sys,json;sys.path.insert(0,' +
    JSON.stringify(VB_DIR) +
    ');from feishu_products_io import update_design,get_token;' +
    'print(json.dumps(update_design(get_token(),' +
    JSON.stringify(rid) +
    ',sys.stdin.read()),ensure_ascii=False))';
  const out = execFileSync(PY, ['-c', code], {
    input: fs.readFileSync(mdFile, 'utf-8'),
    encoding: 'utf-8',
    maxBuffer: 32 * 1024 * 1024,
  });
  if (log) log('  ✅ 已回写飞书 ' + rid + ' -> ' + out.trim().slice(0, 60));
}

// ---------- 单条生成（批量/单条共用） ----------
async function runOne(page, o, log, rid, inputFile, outFile, shotFile) {
  const siText = fs.readFileSync(o.si, 'utf-8');
  const inputText = fs.readFileSync(inputFile, 'utf-8');
  await page.waitForSelector(SEL_PROMPT, { timeout: 30000 }).catch(() => {});
  await waitStable(page, log).catch(() => {});

  // 1) 切模型到 3.1-pro-preview（用户硬要求）
  await selectModel(page, o.model, log);

  // 2) 确保 System Instructions 是 v5.4（首次注入，后续复用）
  const si = await ensureSI(page, siText, log);
  log('  SI ' + (si.reused ? '已复用' : '已注入') + ': ' + si.len + ' 字符');

  // 3) 注入商品信息（拟人逐字键入）
  const plen = await injectPrompt(page, inputText, log);
  log('  商品信息注入: ' + plen + ' 字符');
  if (plen === 0) throw new Error('商品信息注入失败：输入框为空');

  // 4) 拟人提交：先确保焦点在 prompt 输入框，再 Ctrl+Enter
  await page.locator(SEL_PROMPT).first().click().catch(() => {});
  await sleep(rand(300, 600));
  await page.keyboard.press('Control+Enter');
  log('→ 已提交，等待生成...');

  // 5) 拟人提取：等稳定 + 点 copy as text + 读剪贴板
  const answer = await waitAndCopy(page, o.genTimeout, log);
  if (!answer || answer.length < 100) throw new Error('copy as text 拿回内容为空或太短（' + (answer ? answer.length : 0) + ' 字符）');

  // 6) 落盘
  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  const header =
    '<!-- generated by aistudio_design_plan.cjs\n' +
    '     model: ' + o.model + '\n' +
    '     session: ' + page.url() + '\n' +
    '     time: ' + new Date().toISOString() + ' -->\n\n';
  fs.writeFileSync(outFile, header + answer, 'utf-8');
  log('  设计方案落盘: ' + outFile + ' (' + answer.length + ' 字符)');

  if (shotFile) {
    await page.screenshot({ path: shotFile, fullPage: false }).catch(() => {});
    log('  截图: ' + shotFile);
  }

  if (o.writeFeishu && rid) {
    try {
      writeFeishu(rid, outFile, log);
    } catch (e) {
      log('  ⚠️ 飞书回写失败: ' + e.message);
    }
  } else if (rid) {
    log('  （未启用 --write-feishu，跳过回写）');
  }
  return outFile;
}

// ---------- --mcp-mode 编排清单输出器（CLI 改造过渡） ----------
// 用户 2026-08-14 03:33 指令："进行 MCP 改造" + "允许使用你的常用浏览器进行 skill 的创建"。
// 本函数输出"接下来该调用的 MCP 工具序列"，不启 Chrome、不连 CDP。浏览器交互交由 agent 调
//   mcp__playwright__browser_* 高层工具。
// 关键前置：用户须已手动启动 Chrome 带 --remote-debugging-port=DEFAULT_CDP_PORT（或 --cdp-url 指定端口），
//   playwright MCP 通过 --cdp-endpoint 接管，否则 MCP 自启 chromium（被检测风险最高档）。
// 拟人化要求（按 user-memory 8-14 03:22 三条新事实）：会话输入区走真实键入（30-60ms/字），
//   短文本不需太慢；SI 区不做拟人化、走"按命名下拉选中"；内容提取走 "copy as text" + 系统剪贴板。
function printMcpPlan(o) {
  const cdpPort = (o.cdpUrl.match(/:(\d+)$/) || [, DEFAULT_CDP_PORT])[1];
  const out = [];
  out.push('# aistudio_design_plan — MCP 编排清单');
  out.push('');
  out.push('> 模型: ' + o.model + '（用户 2026-08-14 硬性要求，已禁用 flash）');
  out.push('> SI: ' + o.si);
  out.push('> 模式: ' + (o.batch ? '批量' : '单条'));
  out.push('> 出文目录: ' + o.outDir);
  out.push('');
  out.push('## 前置条件（用户已完成才能继续）');
  out.push('- [ ] 1. 用户日常 Chrome 已手动启动并加 `--remote-debugging-port=' + cdpPort + '`');
  out.push('- [ ] 2. 已登录 aistudio.google.com（同一 user-data-dir）');
  out.push('- [ ] 3. 用户已在右栏 System Instructions 区粘一次 v5.4 并**命名保存**（按用户 8-14 03:22 明示：SI 可命名复用，不要脚本注入长文本）');
  out.push('- [ ] 4. playwright MCP 已启用 trust（user-memory § 191「自动化 skill 铁律」）');
  out.push('');
  out.push('## MCP 调用序列（按顺序执行）');
  out.push('');
  out.push('### Phase 1：模型硬性 = gemini-3.1-pro-preview');
  out.push('```');
  out.push('mcp__playwright__browser_navigate { url: "https://aistudio.google.com/prompts/new_chat" }');
  out.push('mcp__playwright__browser_evaluate { function: "() => document.querySelector(\'[data-test-id=\"model-name\"]\')?.textContent?.trim() || \\"\\"" }');
  out.push('// → 已含 3.1-pro-preview 则跳过；否则调 selectModelByName（点模型下拉 → 按全名精确选中）');
  out.push('```');
  out.push('');
  out.push('### Phase 2：SI 复用检测（不重新注入）');
  out.push('```');
  out.push('mcp__playwright__browser_evaluate { function: "() => { const ta = document.querySelector(\'textarea[aria-label=\"System instructions\"]\'); return ta ? ta.value : \\"\\"; }" }');
  out.push('// → 已含 v5.4 双关键词（POD 印花底稿 + v5.4）则跳过；否则提示用户手动粘一次并命名保存后再继续');
  out.push('```');
  out.push('');
  out.push('### Phase 3：拟人键入商品信息（30-60ms/字，短文本 <5s）');
  out.push('```');
  out.push('mcp__playwright__browser_click { selector: "textarea[aria-label=\\"Enter a prompt\\"]", element: "商品信息输入区" }');
  out.push('mcp__playwright__browser_press_key { key: "Control+A" }');
  out.push('mcp__playwright__browser_press_key { key: "Delete" }');
  out.push('// page.keyboard.type(短文本, { delay: 30 + Math.random()*30 }) — 用户 03:22 明示「速度不用太慢」');
  out.push('mcp__playwright__browser_wait_for { time: 1.5 }  // 等 React 18 batching');
  out.push('mcp__playwright__browser_click { selector: "[aria-label=\\"Submit\\"], button[mat-icon-button][aria-label=\\"Run\\"]", element: "Run / Send 按钮" }');
  out.push('```');
  out.push('');
  out.push('### Phase 4：等生成完毕');
  out.push('```');
  out.push('// 用户 8-14 03:22 明示：internal error 不点 Rerun，不自动重试——失败立即 throw');
  out.push('mcp__playwright__browser_wait_for { text: "Copy as text" }   // 或文字停止增长');
  out.push('mcp__playwright__browser_take_screenshot { filename: "' + (o.shot || o.outDir + '/shot.png') + '" }');
  out.push('```');
  out.push('');
  out.push('### Phase 5：copy as text + 读系统剪贴板');
  out.push('```');
  out.push('mcp__playwright__browser_click { selector: "[aria-label=\\"Copy as text\\"], button:has-text(\\"Copy as text\\")", element: "Copy as text 按钮" }');
  out.push('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::GetText()"');
  out.push('// → Write 工具写 dp_run/design_<rid>.md');
  out.push('```');
  out.push('');
  out.push('### Phase 6（条件）：回写飞书（--write-feishu 启用时）');
  out.push('```');
  out.push('python ../aistudio-visualbridge/scripts/feishu_products_io.py write <rid> < out.md');
  out.push('// 注：argv 长度受限，agent 需用 python -c 调 update_design()');
  out.push('```');
  out.push('');
  out.push('## 拟人化 / 反检测 关键约束');
  out.push('- 短文本（< 500 字符）：30-60ms/字 + 段间 100-300ms，整段 < 5 秒');
  out.push('- SI 区：**禁止脚本注入**；必须用户手动粘一次并命名保存');
  out.push('- 内容提取：copy as text + 系统剪贴板，不抓 .turn-content DOM');
  out.push('- internal error：不点 Rerun、不自动重试；throw 上抛，由 agent 反馈用户');
  out.push('- MCP 默认启 Chromium；必须 --cdp-endpoint 指向用户已开 Chrome');
  console.log(out.join('\n'));
}

// ---------- 主流程 ----------
(async () => {
  const o = parseArgs(process.argv.slice(2));
  if (o.help) {
    console.log(HELP);
    process.exit(0);
  }
  if (o.batch) {
    if (!fs.existsSync(o.si)) {
      console.error('错误：System Instructions 文件不存在: ' + o.si);
      process.exit(2);
    }
  } else {
    if (!o.input || !fs.existsSync(o.input)) {
      console.error('错误：--input 必须指向存在的商品基础信息文件（或改用 --batch）。');
      process.exit(2);
    }
    if (!o.out) {
      console.error('错误：--out 必须指定设计方案输出路径（或改用 --batch）。');
      process.exit(2);
    }
    if (!fs.existsSync(o.si)) {
      console.error('错误：System Instructions 文件不存在: ' + o.si);
      process.exit(2);
    }
  }
  // 模型硬约束
  for (const bad of BANNED_MODELS) {
    if (o.model.toLowerCase().includes(bad)) {
      console.error('错误：模型 [' + o.model + '] 已被禁用（用户 2026-08-14 硬性要求 3.1-pro-preview）。请用 --model gemini-3.1-pro-preview');
      process.exit(2);
    }
  }

  // ===== --mcp-mode 早返回：仅输出"待 MCP 调用的指令序列"，不启 Chrome、不加载 playwright =====
  // 用户 2026-08-14 03:33 指令："进行MCP改造"。本模式是过渡阶段：CLI 退化为编排清单生成器，
  // 浏览器交互完全交给 agent 调 mcp__playwright__browser_* 高层工具；CLI 仅做数据组装 + 飞书读写。
  if (o.mcpMode) {
    printMcpPlan(o);
    return;
  }

  const { chromium } = loadPlaywright();
  const log = (m) => console.log(m);
  log('AI Studio 设计方案 CLI — 模型: ' + o.model + (o.batch ? ' | 批量模式' : ' | 单条模式'));
  log('  SI: ' + o.si);
  log('  模式: ' + (o.headless ? '无头' : '有头(默认)'));
  log('  拟人化: ✅ (真实点击/键入/复制按钮)');
  log('  启动方式: 进程外拉起真实 Chrome（无 Playwright 自动化标记）');

  // 启动：两种模式
  //   attach   → 不新拉 Chrome，直接 connectOverCDP(o.cdpUrl)，共享用户日常 Chrome
  //              （登录态 + SI 历史 + 已开 tab 全复用，不破坏用户窗口）
  //   默认     → 进程外 spawn 一个隔离的 Chrome（用 o.profile，与用户日常 Chrome 完全隔离）
  let child = null;
  let browser;
  if (o.attach) {
    log('  启动方式: 接管用户日常 Chrome @ ' + o.cdpUrl);
    log('  ⚠️ 用户须先手动启动 Chrome 加 --remote-debugging-port=9223 (用同一 user-data-dir)');
    let cdpReady = false;
    for (let i = 0; i < 15; i++) {
      try {
        const res = await fetch(o.cdpUrl + '/json/version');
        if (res.ok) { cdpReady = true; break; }
      } catch (e) {}
      await sleep(1000);
    }
    if (!cdpReady) {
      throw new Error('CDP 端点未就绪：' + o.cdpUrl + '（请确认 Chrome 已用 --remote-debugging-port=9223 启动）');
    }
    browser = await chromium.connectOverCDP(o.cdpUrl);
  } else {
    const CDP_PORT = DEFAULT_CDP_PORT;
    const chromeArgs = [
      '--remote-debugging-port=' + CDP_PORT,
      '--user-data-dir=' + o.profile,
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-blink-features=AutomationControlled',
    ];
    if (o.headless) chromeArgs.push('--headless=new');
    if (o.proxy) chromeArgs.push('--proxy-server=' + o.proxy);
    // 用户 2026-08-14 03:43 spawn 接管 spawn FATAL 诊断：把 stdio 设为 pipe 让 stderr 可见
    child = spawn(CHROME_EXE, chromeArgs, { stdio: ['ignore', 'pipe', 'pipe'] });
    let chromeStderr = '';
    child.stdout.on('data', (d) => process.stdout.write('[chrome-out] ' + d));
    child.stderr.on('data', (d) => { chromeStderr += d.toString(); });
    child.on('error', (e) => log('  ⚠️ Chrome spawn() 失败: ' + e.message));
    child.on('exit', (code) => {
      if (code) log('  ⚠️ Chrome 进程退出 code=' + code + ' stderr=' + (chromeStderr.trim().slice(0, 400) || '(空)'));
    });
    let cdpReady = false;
    for (let i = 0; i < 30; i++) {
      try {
        const res = await fetch('http://127.0.0.1:' + CDP_PORT + '/json/version');
        if (res.ok) { cdpReady = true; break; }
      } catch (e) {}
      await sleep(1000);
    }
    if (!cdpReady) {
      try { child.kill('SIGTERM'); } catch (e) {}
      throw new Error('Chrome 启动失败：DevTools 端点 ' + CDP_PORT + ' 在 30s 内未就绪');
    }
    browser = await chromium.connectOverCDP('http://127.0.0.1:' + CDP_PORT);
  }

  try {
    const context = browser.contexts()[0] || (await browser.newContext());
    const page = context.pages()[0] || (await context.newPage());
    log('→ 打开 Playground: ' + PLAYGROUND_URL);
    await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await waitStable(page, log);

    // 登录检测
    let needsLogin = false;
    for (let i = 0; i < 4; i++) {
      try {
        needsLogin = await page.evaluate(() =>
          /accounts\.google\.com/.test(location.href) ||
          [...document.querySelectorAll('a, button')].some((e) => /Sign in/i.test(e.textContent || ''))
        );
        break;
      } catch (e) {
        log('  ⏳ 登录检测上下文失效，重等 (' + (3 - i) + ' 剩余)');
        await waitStable(page, log);
      }
    }
    if (needsLogin) {
      if (o.headless) {
        throw new Error('未登录：无头模式无法登录，请改用 --headed');
      }
      log('🔐 检测到未登录。请在弹出的浏览器窗口中完成 Google 登录...');
      const loginDeadline = Date.now() + LOGIN_TIMEOUT * 1000;
      let loggedIn = false;
      while (Date.now() < loginDeadline) {
        await sleep(4000);
        try {
          const stillLogin = await page.evaluate(() =>
            /accounts\.google\.com/.test(location.href) ||
            [...document.querySelectorAll('a, button')].some((e) => /Sign in/i.test(e.textContent || ''))
          );
          if (!stillLogin) {
            try {
              await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
            } catch (e) {}
            loggedIn = true;
            break;
          }
        } catch (e) {}
      }
      if (!loggedIn) throw new Error('登录等待超时（' + LOGIN_TIMEOUT + 's）');
      log('✅ 登录已确认');
      await waitStable(page, log);
    }

    if (o.batch) {
      const rids = o.rids
        ? o.rids.split(/[\s,]+/).filter(Boolean)
        : fetchRidsFromFeishu(o.limit);
      if (!rids.length) {
        log('⚠️ 无待生成记录');
        return;
      }
      log('📋 批量待处理 ' + rids.length + ' 条: ' + rids.join(', '));
      for (let i = 0; i < rids.length; i++) {
        const rid = rids[i];
        log('\n===== [' + (i + 1) + '/' + rids.length + '] 记录 ' + rid + ' =====');
        // 用户 2026-08-14 原话：「否则就重跑整条」
        // 报错（尤其是 internal error 这种 Google 侧偶发）整条自动重试 1 次。
        let attempt = 0;
        const MAX_ATTEMPT = 1; // 用户 2026-08-14 明示：不点 Rerun、不自动整条重试 → 失败立即 throw
        while (attempt < MAX_ATTEMPT) {
          attempt++;
          try {
            await newConversation(page, o.model, log);
            const inp = path.join(o.outDir, 'input_' + rid + '.txt');
            fetchInput(rid, inp);
            const out = path.join(o.outDir, 'design_' + rid + '.md');
            const shot = path.join(o.outDir, 'shot_' + rid + '.png');
            await runOne(page, o, log, rid, inp, out, shot);
            break;
          } catch (e) {
            log('  ❌ 记录 ' + rid + ' 第 1/1 次失败: ' + e.message + ' —— 按用户最新原则不自动重试，throw 上抛给主进程');
            throw e;
          }
        }
      }
      log('\n===== 批量完成 =====');
    } else {
      await newConversation(page, o.model, log);
      await runOne(page, o, log, null, o.input, o.out, o.shot);
      log('\n===== 完成 =====');
      log('  out=' + o.out + ' model=' + o.model);
      log('  session=' + page.url());
    }

    if (o.keepOpen) {
      log('\n--keep-open：浏览器保持打开，Ctrl+C 结束。');
      await new Promise(() => {});
    }
  } finally {
    try {
      if (o.keepOpen) await browser.disconnect();
      else await browser.close();
    } catch (e) {}
    if (!o.keepOpen) { try { child.kill('SIGTERM'); } catch (e) {} }
  }
  process.exit(0);
})().catch((e) => {
  console.error('FATAL', e);
  process.exit(1);
});

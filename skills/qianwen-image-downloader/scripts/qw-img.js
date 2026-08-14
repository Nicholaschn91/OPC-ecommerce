#!/usr/bin/env node
'use strict';
/*
 * 千问/通义 无水印原图抓取 CLI
 * 流程：open(起浏览器+注入嗅探) → [login 手动/复用 profile] → generate(发 prompt) → list(读原图URL) → download(落地) → close
 * 也支持一键 run：open → generate → list → download → close（依赖已登录的持久 profile）
 *
 * 依赖：playwright-core（npm i playwright-core），以及本目录的 qianwen-sniff.js
 */
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawnSync } = require('child_process');

const ROOT = __dirname;
const SNIFF = fs.readFileSync(path.join(ROOT, 'qianwen-sniff.js'), 'utf8');
const CDP = 'http://127.0.0.1:9222';
const TARGET = process.env.QW_URL || 'https://www.qianwen.com/chat';
const PROFILE = process.env.QW_PROFILE || path.join(ROOT, 'cdp-profile');

// ---- 参数解析 ----
function parseArgs(argv) {
  const o = { _: [] };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const k = a.slice(2);
      const n = argv[i + 1];
      if (n !== undefined && !n.startsWith('--')) { o[k] = n; i++; }
      else o[k] = true;
    } else {
      o._.push(a);
    }
  }
  return o;
}

// ---- 环境探测 ----
function chromePath() {
  if (process.env.QW_CHROME && fs.existsSync(process.env.QW_CHROME)) return process.env.QW_CHROME;
  const base = path.join(os.homedir(), '.agent-browser', 'browsers');
  if (fs.existsSync(base)) {
    const dirs = fs.readdirSync(base).filter(d => d.startsWith('chrome-')).sort().reverse();
    for (const d of dirs) {
      const p = path.join(base, d, 'chrome.exe');
      if (fs.existsSync(p)) return p;
    }
  }
  try { return chromium.executablePath(); } catch (e) { return null; }
}
function proxyOption() {
  // 千问无需代理（IP 铁律只限 Etsy），默认直连；仅显式设 QW_PROXY 才走代理
  const p = process.env.QW_PROXY;
  if (!p || process.env.QW_NO_PROXY) return undefined;
  return { server: p };
}
function browserArgs() {
  return ['--no-sandbox', '--remote-debugging-port=9222', '--window-size=1280,900'];
}

// ---- 连接已运行的浏览器 ----
async function connect() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const pages = ctx.pages();
  const page = pages.filter(p => /qianwen|tongyi/.test(p.url()))[0] || pages[0];
  const has = await page.evaluate(() => !!window.__qw);
  if (!has) { await page.evaluate(SNIFF); console.log('[重新注入嗅探]'); }
  return { browser, page };
}

// 读取并分类（与实测一致：img && !watermark = 无水印原图）
async function readClean(page) {
  const data = await page.evaluate(() => window.__qw || []);
  const clean = data.filter(d => d.img && !d.watermark);
  const wm = data.filter(d => d.img && d.watermark);
  return { data, clean, wm };
}

// ---- 子命令：open ----
async function openCmd(o) {
  const cp = chromePath();
  if (!cp) { console.error('未找到 Chrome，请设置 QW_CHROME 环境变量'); process.exit(1); }
  const context = await chromium.launchPersistentContext(PROFILE, {
    headless: !!o.headless,
    executablePath: cp,
    proxy: proxyOption(),
    viewport: { width: 1280, height: 900 },
    args: browserArgs(),
  });
  const page = context.pages()[0] || await context.newPage();
  await page.addInitScript(SNIFF); // 所有后续导航（含登录后 SPA 跳转）都注入
  await page.goto(TARGET, { waitUntil: 'domcontentloaded' });
  console.log('=== BROWSER OPEN ===');
  console.log('URL:', page.url());
  console.log('CDP:', CDP, '| 登录态缓存:', PROFILE);
  if (o.headless) {
    console.log('无头模式：等待 90s 让页面加载/登录态生效...');
    await page.waitForTimeout(90000);
    await context.close();
    console.log('=== 无头窗口已关闭 ===');
  } else {
    const mins = parseInt(o.timeout || '20', 10);
    console.log(`有头模式：窗口已弹出，请登录并生成图片。`);
    console.log(`保持 ${mins} 分钟后自动关闭；或另开终端执行: node qw-img.js close`);
    await page.waitForTimeout(mins * 60000);
    await context.close();
    console.log('=== 已关闭 ===');
  }
}

// ---- 进入 AI生图 模式 ----
async function enterAIImageMode(page) {
  // 检查是否已在 AI生图 模式（底部栏有“参考图”按钮）
  const already = await page.evaluate(() => !![...document.querySelectorAll('*')].find(el => /参考图/.test(el.textContent||'') && el.children.length <= 3 && (el.textContent||'').trim().length < 10));
  if (already) { console.log('[AI生图] 已在 AI生图 模式'); return; }

  // 策略1：直接点击 aria-label="AI生图" 按钮（底部栏模式切换按钮）
  try {
    await page.getByLabel('AI生图').click({ force: true, timeout: 5000 });
    await page.waitForTimeout(1500);
    // 验证是否激活（检查是否出现“参考图”或“创意生图”）
    const active = await page.evaluate(() => /参考图|创意生图|智能修图/.test(document.body.innerText));
    if (active) { console.log('[AI生图] 已通过按钮进入模式'); return; }
  } catch (_) {}

  // 策略2：点“更多”→ 点下拉中的“AI生图”菜单项
  try { await page.getByText('更多', { exact: true }).first().click({ timeout: 3000 }); } catch (_) {}
  await page.waitForTimeout(800);
  const items = await page.getByText('AI生图').all();
  // 取最后一个（通常是下拉菜单项，前面的可能是底部栏按钮）
  for (let i = items.length - 1; i >= 0; i--) {
    try { await items[i].click({ timeout: 2000, force: true }); console.log('[AI生图] 已通过下拉菜单进入'); return; } catch (_) {}
  }
  console.warn('[AI生图] 未确认进入模式，继续尝试...');
}

// ---- 上传参考图（图生图）----
async function uploadReferenceImage(page, imgPath) {
  if (!fs.existsSync(imgPath)) { console.error(`底图文件不存在: ${imgPath}`); process.exit(1); }
  // 点底部栏的“参考图”按钮（宽松匹配，不要求 exact）
  let clicked = false;
  // 策略A：getByText 不用 exact
  const refs = await page.getByText(/参考图/).all();
  for (const r of refs) {
    try { await r.click({ timeout: 3000, force: true }); clicked = true; break; } catch (_) {}
  }
  // 策略B：evaluate 找文本 == '参考图' 的可点击元素
  if (!clicked) {
    clicked = await page.evaluate(() => {
      const els = [...document.querySelectorAll('button, [role=button], span, div')];
      for (const el of els) {
        if ((el.textContent || '').trim() === '参考图' && el.offsetParent !== null) {
          el.click(); return true;
        }
      }
      return false;
    });
    if (clicked) console.log('[参考图] 通过 evaluate 点击');
  }
  if (!clicked) { console.error('未找到"参考图"按钮'); return false; }
  await page.waitForTimeout(800);

  // 用 file chooser 拦截上传
  const [fileChooser] = await Promise.all([
    page.waitForEvent('filechooser', { timeout: 5000 }),
  ]).catch(() => []);
  if (fileChooser) {
    await fileChooser.setFiles(imgPath);
    console.log(`[参考图] 已上传: ${path.basename(imgPath)}`);
    await page.waitForTimeout(1000);
    return true;
  }
  // 兜底：直接找 input[type=file]
  const inputs = await page.$$('input[type=file]');
  if (inputs.length > 0) {
    await inputs[0].setInputFiles(imgPath);
    console.log(`[参考图] 已通过 input 上传: ${path.basename(imgPath)}`);
    return true;
  }
  console.error('未触发文件选择器');
  return false;
}

// ---- 子命令：generate ----
async function doGenerate(page, prompt, opts) {
  // 图生图：先进入 AI生图 模式 + 上传参考图
  if (opts.img) {
    await enterAIImageMode(page);
    await uploadReferenceImage(page, opts.img);
  }

  const sel = await page.evaluate(() => {
    if (document.querySelector('textarea')) return 'textarea';
    if (document.querySelector('[role="textbox"], [contenteditable="true"], [contenteditable=""]')) return 'contenteditable';
    return null;
  });
  if (!sel) { console.error('未找到输入框（textarea / contenteditable）'); return false; }
  if (sel === 'textarea') await page.fill('textarea', prompt);
  else await page.fill('[role="textbox"]', prompt).catch(async () => {
    // 兜底：用 click + type
    await page.click('[role="textbox"]');
    await page.keyboard.type(prompt, { delay: 10 });
  });
  await page.keyboard.press('Enter');
  // 轮询等待新原图出现（最多 60s）
  const before = (await readClean(page)).clean.length;
  let waited = 0;
  while (waited < 60000) {
    await page.waitForTimeout(3000); waited += 3000;
    const now = (await readClean(page)).clean.length;
    if (now > before) { console.log(`已生成：原图数 ${before} → ${now}`); return true; }
  }
  console.log('已发送 prompt，但未检测到新原图（可能还在生成或选择器变化）');
  return true;
}
async function generateCmd(o) {
  const prompt = o.prompt || o._.join(' ');
  if (!prompt) { console.error('请传入 prompt，如: node qw-img.js generate "画一只猫"'); process.exit(1); }
  if (o.img && !fs.existsSync(o.img)) { console.error(`底图文件不存在: ${o.img}`); process.exit(1); }
  const { browser, page } = await connect();
  await doGenerate(page, prompt, { img: o.img });
  await browser.close();
}

// ---- 子命令：list ----
async function listCmd(o) {
  const { browser, page } = await connect();
  const { data, clean, wm } = await readClean(page);
  console.log(`总 URL: ${data.length} | 无水印原图: ${clean.length} | 水印图: ${wm.length}`);
  const limit = parseInt(o.limit || '30', 10);
  clean.slice(0, limit).forEach((d, i) => console.log(`${i + 1}. [${d.where}] ${d.url}`));
  if (o.json) {
    const f = o.json === true ? path.join(ROOT, 'qw-clean.json') : o.json;
    fs.writeFileSync(f, JSON.stringify(clean, null, 2));
    console.log('已写出:', f);
  }
  await browser.close();
}

// ---- 子命令：download ----
function proxyForCurl() {
  // 千问无需代理，默认直连；仅显式设 QW_PROXY 才走代理（curl 下载原图用）
  const p = process.env.QW_PROXY;
  if (!p || process.env.QW_NO_PROXY) return [];
  return ['-x', p];
}
async function downloadCmd(o) {
  const { browser, page } = await connect();
  const { clean } = await readClean(page);
  await browser.close();
  const out = o.out || path.join(ROOT, 'qianwen-dl');
  fs.mkdirSync(out, { recursive: true });
  console.log(`下载 ${clean.length} 张到 ${out}`);
  let ok = 0, fail = 0;
  for (const d of clean) {
    const u = d.url;
    const m = u.match(/\.(png|jpe?g|webp|gif|bmp)(?:\?|$)/i);
    const ext = m ? m[1].toLowerCase() : 'jpg';
    const name = 'qw_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7) + '.' + ext;
    const fp = path.join(out, name);
    const r = spawnSync('curl', ['-sL', '--max-time', '60', '-o', fp, ...proxyForCurl(), u], {
      stdio: 'ignore', env: process.env,
    });
    if (r.status === 0 && fs.existsSync(fp) && fs.statSync(fp).size > 0) ok++;
    else { fail++; if (fs.existsSync(fp)) fs.unlinkSync(fp); }
  }
  console.log(`完成：成功 ${ok}，失败 ${fail}`);
}

// ---- 子命令：close ----
async function closeCmd() {
  try {
    const b = await chromium.connectOverCDP(CDP);
    await b.close();
    console.log('已关闭浏览器');
  } catch (e) {
    console.log('关闭失败（可能未运行）:', e.message);
  }
}

// ---- 子命令：run（一键）----
async function runCmd(o) {
  const cp = chromePath();
  if (!cp) { console.error('未找到 Chrome，请设置 QW_CHROME'); process.exit(1); }
  const context = await chromium.launchPersistentContext(PROFILE, {
    headless: !!o.headless,
    executablePath: cp,
    proxy: proxyOption(),
    viewport: { width: 1280, height: 900 },
    args: browserArgs(),
  });
  const page = context.pages()[0] || await context.newPage();
  await page.addInitScript(SNIFF);
  await page.goto(TARGET, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(o.headless ? 8000 : 4000);
  if (o.prompt) await doGenerate(page, o.prompt, { img: o.img });
  const { clean } = await readClean(page);
  console.log(`无水印原图: ${clean.length}`);
  if (o.json) {
    const f = o.json === true ? path.join(ROOT, 'qw-clean.json') : o.json;
    fs.writeFileSync(f, JSON.stringify(clean, null, 2));
  }
  if (!o['no-download']) {
    const out = o.out || path.join(ROOT, 'qianwen-dl');
    fs.mkdirSync(out, { recursive: true });
    let ok = 0, fail = 0;
    for (const d of clean) {
      const u = d.url;
      const m = u.match(/\.(png|jpe?g|webp|gif|bmp)(?:\?|$)/i);
      const ext = m ? m[1].toLowerCase() : 'jpg';
      const name = 'qw_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7) + '.' + ext;
      const fp = path.join(out, name);
      const r = spawnSync('curl', ['-sL', '--max-time', '60', '-o', fp, ...proxyForCurl(), u], { stdio: 'ignore', env: process.env });
      if (r.status === 0 && fs.existsSync(fp) && fs.statSync(fp).size > 0) ok++;
      else { fail++; if (fs.existsSync(fp)) fs.unlinkSync(fp); }
    }
    console.log(`下载完成：成功 ${ok}，失败 ${fail} -> ${out}`);
  }
  await context.close();
  console.log('=== run 完成，浏览器已关闭 ===');
}

// ---- 入口 ----
const cmd = process.argv[2];
const o = parseArgs(process.argv);
(async () => {
  switch (cmd) {
    case 'open': await openCmd(o); break;
    case 'generate': await generateCmd(o); break;
    case 'list': await listCmd(o); break;
    case 'download': await downloadCmd(o); break;
    case 'close': await closeCmd(); break;
    case 'run': await runCmd(o); break;
    default:
      console.log(`千问/通义 无水印原图抓取 CLI

用法: node qw-img.js <command> [options]

命令（每个步骤可独立执行）:
  open                启动浏览器窗口 + 注入嗅探 + 打开千问页（有头模式，等登录/生成）
  generate "<文本>"   在输入框发送生图 prompt（--img PATH 可选，图生图）
  list [--json f]     读取并列出抓到的无水印原图 URL（--json 写出到文件）
  download [--out D]  下载全部无水印原图到本地（默认 ./qianwen-dl）
  close               关闭浏览器
  run --prompt "..."  一键：open→generate→list→download→close（依赖已登录的持久 profile）

选项:
  --headless          无头模式（run/open 可用，需已登录 profile）
  --timeout N         open 有头模式保持分钟数（默认 20）
  --out DIR           下载目录
  --json [f]          把原图 URL 写成 JSON
  --limit N           list 展示条数（默认 30）
  --no-download       run 时不下载，只列出
  --img PATH          图生图：指定底图路径（generate / run 可用）

环境变量:
  QW_CHROME   Chrome 路径（默认自动探测 ~/.agent-browser/browsers/chrome-*）
  QW_PROXY    代理地址（默认直连；仅显式设置才走代理，用于需代理的特殊场景）
  QW_URL      目标页（默认 https://www.qianwen.com/chat）
  QW_PROFILE  登录态缓存目录（默认 ./cdp-profile，首次手动登录后自动复用）
`);
  }
})().catch(e => { console.error('错误:', e.message); process.exit(1); });

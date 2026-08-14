#!/usr/bin/env node
/**
 * doubao-capture.cjs  —  Doubao 无水印原图抓取 CLI  (READ-ONLY)
 *
 * 作用：从指定的豆包对话页（URL 列表）中，拦截其对话接口 JSON，
 *       抽取 image_ori_raw.url（无水印全分辨率原图），下载到指定目录。
 *
 * 只读性（Agent 只能读取）：本工具只做「读取对话接口 + 下载原图」，
 *       绝不会向豆包发送 / 发布 / 修改任何内容。
 *
 * 依赖：Node >= 18（需全局 fetch）、playwright（自动从已知路径或 PLAYWRIGHT_LIB 解析）。
 */
'use strict';
const fs = require('fs');
const path = require('path');

// ---------- 配置默认值 ----------
const DEFAULT_PROFILE =
  'C:/Users/Administrator.DESKTOP-AHRMISP/WorkBuddy/2026-08-01-16-56-12/doubao-profile';
const CHROME_EXE = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const REFERRER = 'https://www.doubao.com/';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36';

// ---------- playwright 解析（多候选，避免硬编码单点） ----------
function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_LIB,
    'playwright',
    'C:/Users/Administrator.DESKTOP-AHRMISP/AppData/Local/npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright',
    'C:/Users/Administrator.DESKTOP-AHRMISP/.workbuddy/binaries/node/versions/22.22.2/node_modules/@playwright/cli/node_modules/playwright',
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
    '找不到 playwright。设置环境变量 PLAYWRIGHT_LIB 指向其目录，或确认 npm-cache 中存在 playwright。\n' +
      '最后错误: ' + (lastErr && lastErr.message)
  );
}

// ---------- 参数解析 ----------
function parseArgs(argv) {
  const o = {
    url: null,
    list: null,
    out: null,
    profile: DEFAULT_PROFILE,
    headless: true,
    noDownload: false,
    flat: false,
    timeout: 20000,
    scroll: 3,
    concurrency: 4,
    discover: false,
    discoverOut: null,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const kv = (k, def) => {
      if (a === k) return argv[++i];
      if (a.startsWith(k + '=')) return a.slice(k.length + 1);
      return def;
    };
    if (a === '--url') o.url = argv[++i];
    else if (a.startsWith('--url=')) o.url = a.slice('--url='.length);
    else if (a === '--list') o.list = argv[++i];
    else if (a.startsWith('--list=')) o.list = a.slice('--list='.length);
    else if (a === '--out') o.out = argv[++i];
    else if (a.startsWith('--out=')) o.out = a.slice('--out='.length);
    else if (a === '--profile') o.profile = argv[++i];
    else if (a.startsWith('--profile=')) o.profile = a.slice('--profile='.length);
    else if (a === '--headed') o.headless = false;
    else if (a === '--no-download') o.noDownload = true;
    else if (a === '--flat') o.flat = true;
    else if (a === '--timeout') o.timeout = parseInt(argv[++i], 10);
    else if (a.startsWith('--timeout=')) o.timeout = parseInt(a.slice('--timeout='.length), 10);
    else if (a === '--scroll') o.scroll = parseInt(argv[++i], 10);
    else if (a.startsWith('--scroll=')) o.scroll = parseInt(a.slice('--scroll='.length), 10);
    else if (a === '--concurrency') o.concurrency = parseInt(argv[++i], 10);
    else if (a.startsWith('--concurrency=')) o.concurrency = parseInt(a.slice('--concurrency='.length), 10);
    else if (a === '--discover') o.discover = true;
    else if (a.startsWith('--discover=')) { o.discover = true; o.discoverOut = a.slice('--discover='.length); }
    else if (a === '--discover-out') o.discoverOut = argv[++i];
    else if (a === '-h' || a === '--help') { o.help = true; }
  }
  return o;
}

const HELP = `
doubao-capture  —  Doubao 无水印原图抓取 (READ-ONLY：仅读取对话接口 + 下载原图，不向豆包写入任何内容)

用法:
  node doubao-capture.cjs --url <对话URL> [--out <保存目录>] [选项]
  node doubao-capture.cjs --list <url清单文件> [--out <保存目录>] [选项]
  node doubao-capture.cjs --discover [--discover-out <文件>] [--out <保存目录>] [选项]

选项:
  --url <url>            单个豆包对话 URL (https://www.doubao.com/chat/<id>)
  --list <file>          含多个对话 URL 的文件（每行一个）
  --out <dir>            保存根目录（默认 ./doubao_captures），每个对话落在 <dir>/<convId>/ 下
  --flat                 直接把文件放进 --out（不建 <convId> 子目录）
  --profile <dir>        用户数据目录（默认 doubao-profile，内含登录态）
  --headed               有头模式（默认无头）
  --no-download          仅抽取并写出 raw_urls.txt，不下载图片
  --timeout <ms>         每页等待超时（默认 20000）
  --scroll <n>           加载后滚动次数以触发懒加载（默认 3）
  --concurrency <n>      并发下载数（默认 4）
  --discover             从豆包侧栏抓取对话 URL 清单（写 --discover-out 或 stdout）
  -h, --help             显示帮助
`;

// ---------- 递归抽取 image_ori_raw.url ----------
function collectRawUrls(node, out) {
  if (node === null || typeof node !== 'object') return;
  if (Array.isArray(node)) {
    for (const v of node) collectRawUrls(v, out);
    return;
  }
  for (const [k, v] of Object.entries(node)) {
    if (k === 'image_ori_raw' && v && typeof v === 'object' && typeof v.url === 'string') {
      out.add(v.url);
    }
    collectRawUrls(v, out);
  }
}

function convIdFromUrl(url) {
  const m = url.match(/chat\/([A-Za-z0-9_-]+)/);
  return m ? m[1] : 'conv_' + Date.now();
}

const EXT_RE = /\.(jpe?g|png|webp|gif|bmp)(?:\?|$)/i;
function extOf(url) {
  const m = url.match(EXT_RE);
  return m ? m[1].toLowerCase() : 'jpg';
}

// ---------- 并发下载 ----------
async function downloadAll(urls, outDir, concurrency, log) {
  const results = [];
  let idx = 0;
  async function worker() {
    while (idx < urls.length) {
      const i = idx++;
      const url = urls[i];
      const ext = extOf(url);
      const file = path.join(outDir, `raw_${String(i + 1).padStart(3, '0')}.${ext}`);
      try {
        const res = await fetch(url, {
          headers: { Referer: REFERRER, 'User-Agent': UA },
          redirect: 'follow',
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const buf = Buffer.from(await res.arrayBuffer());
        fs.writeFileSync(file, buf);
        results.push({ i: i + 1, ok: true, file, size: buf.length, http: res.status });
        log(`  [${i + 1}/${urls.length}] OK  ${buf.length} bytes -> ${path.basename(file)}`);
      } catch (e) {
        results.push({ i: i + 1, ok: false, error: String(e.message || e) });
        log(`  [${i + 1}/${urls.length}] FAIL ${String(e.message || e)}`);
      }
    }
  }
  const n = Math.max(1, Math.min(concurrency, urls.length || 1));
  await Promise.all(Array.from({ length: n }, () => worker()));
  return results;
}

// ---------- 单对话捕获 ----------
async function captureOne(browser, url, opts, log) {
  const page = await browser.newPage();
  const found = new Set();
  page.on('response', async (response) => {
    try {
      const ct = (response.headers()['content-type'] || '').toLowerCase();
      if (!ct.includes('json') && !ct.includes('javascript')) return;
      const text = await response.text();
      let obj;
      try { obj = JSON.parse(text); } catch { return; }
      collectRawUrls(obj, found);
    } catch { /* ignore */ }
  });

  log(`→ 打开 ${url}`);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: opts.timeout });
  // 等待对话接口返回
  await page.waitForTimeout(8000);
  // 滚动触发懒加载，再捕获一轮
  for (let s = 0; s < opts.scroll; s++) {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1500);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(2000);

  await page.close();
  return [...found];
}

// ---------- discover 侧栏对话 URL ----------
async function discover(browser, opts, log) {
  const page = await browser.newPage();
  log('→ 打开豆包对话列表 /chat/');
  await page.goto('https://www.doubao.com/chat/', { waitUntil: 'domcontentloaded', timeout: opts.timeout });
  await page.waitForTimeout(6000);
  const links = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('a[href]').forEach((a) => {
      const h = a.getAttribute('href') || '';
      if (/\/chat\/[A-Za-z0-9_-]+/.test(h)) {
        const u = h.startsWith('http') ? h : 'https://www.doubao.com' + h;
        out.push(u);
      }
    });
    return [...new Set(out)];
  });
  await page.close();
  return links;
}

// ---------- 主流程 ----------
(async () => {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.help) { console.log(HELP); process.exit(0); }

  const { chromium } = loadPlaywright();
  const log = (m) => console.log(m);

  if (opts.discover) {
    const browser = await chromium.launchPersistentContext(opts.profile, {
      headless: opts.headless,
      executablePath: CHROME_EXE,
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    });
    try {
      const links = await discover(browser, opts, log);
      if (opts.discoverOut) {
        fs.writeFileSync(opts.discoverOut, links.join('\n') + '\n');
        log(`已写出 ${links.length} 个对话 URL -> ${opts.discoverOut}`);
      } else {
        log(`发现 ${links.length} 个对话 URL：`);
        links.forEach((l) => log('  ' + l));
      }
    } finally {
      await browser.close();
    }
    process.exit(0);
  }

  // 收集输入 URL
  const urls = [];
  if (opts.url) urls.push(opts.url.trim());
  if (opts.list) {
    const txt = fs.readFileSync(opts.list, 'utf-8');
    txt.split(/\r?\n/).map((s) => s.trim()).filter(Boolean).forEach((u) => urls.push(u));
  }
  if (urls.length === 0) {
    console.error('错误：必须通过 --url 或 --list 指定至少一个对话 URL。用 -h 查看帮助。');
    process.exit(2);
  }
  log(`共 ${urls.length} 个对话待抓取（headless=${opts.headless}）`);

  const browser = await chromium.launchPersistentContext(opts.profile, {
    headless: opts.headless,
    executablePath: CHROME_EXE,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });

  const summary = [];
  try {
    for (const url of urls) {
      const cid = convIdFromUrl(url);
      const outDir = opts.flat ? opts.out : path.join(opts.out || './doubao_captures', cid);
      fs.mkdirSync(outDir, { recursive: true });

      const rawUrls = await captureOne(browser, url, opts, log);
      log(`  抽取到 ${rawUrls.length} 个无水印原图 URL`);
      fs.writeFileSync(path.join(outDir, 'raw_urls.txt'), rawUrls.join('\n') + '\n');

      let files = [];
      if (!opts.noDownload && rawUrls.length) {
        log('  开始下载…');
        const r = await downloadAll(rawUrls, outDir, opts.concurrency, log);
        files = r;
      }
      const okCount = files.filter((f) => f.ok).length;
      summary.push({ url, cid, count: rawUrls.length, ok: okCount, outDir });
      log(`  完成：${outDir}  (原图 ${rawUrls.length}，下载成功 ${okCount})`);
    }
  } finally {
    await browser.close();
  }

  log('\n===== 汇总 =====');
  summary.forEach((s) => log(`  ${s.cid}: ${s.count} 原图, ${s.ok} 下载成功 -> ${s.outDir}`));
  process.exit(0);
})().catch((e) => {
  console.error('FATAL', e);
  process.exit(1);
});

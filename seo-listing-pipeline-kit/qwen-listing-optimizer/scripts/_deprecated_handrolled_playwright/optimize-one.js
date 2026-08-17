#!/usr/bin/env node
'use strict';
// 单条 listing 优化：无头 Chromium + 千问 Qwen3.8-Max + 每条独立新对话窗口
const fs = require('fs');
const path = require('path');
const os = require('os');

// 载入 playwright-core（优先本地，回退到 qianwen-image-downloader 已装依赖）
function loadChromium() {
  try { return require('playwright-core').chromium; }
  catch (e) {
    const fb = process.env.QW_PW_CORE ||
      'C:/Users/Administrator.DESKTOP-AHRMISP/WorkBuddy/2026-07-16-11-36-41/qianwen-image-downloader/node_modules/playwright-core';
    return require(fb).chromium;
  }
}
const chromium = loadChromium();

function findChrome() {
  const dir = path.join(os.homedir(), '.agent-browser', 'browsers');
  if (fs.existsSync(dir)) {
    const l = fs.readdirSync(dir).filter(d => d.startsWith('chrome'))
      .map(d => path.join(dir, d, 'chrome.exe')).filter(p => fs.existsSync(p));
    if (l.length) return l[0];
  }
  try { return chromium.executablePath(); } catch (e) { return null; }
}

function parseArgs(argv) {
  const o = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      const k = argv[i].slice(2);
      const v = (argv[i + 1] && !argv[i + 1].startsWith('--')) ? argv[++i] : true;
      o[k] = v;
    }
  }
  return o;
}

// 解析 --images：目录（扫描图片）或单文件
function resolveImages(spec) {
  if (!spec) return [];
  try {
    const p = path.resolve(spec);
    if (fs.statSync(p).isDirectory()) {
      return fs.readdirSync(p)
        .filter(f => /\.(jpe?g|png|webp)$/i.test(f))
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
        .map(f => path.join(p, f));
    }
    if (fs.existsSync(p)) return [p];
  } catch (e) { console.log('[附件] 解析失败:', e.message); }
  return [];
}

// 上传基材图作垫图；失败降级纯文本（不阻断优化）
async function uploadAttachments(page, imagePaths) {
  if (!imagePaths.length) return false;
  // 先注册 filechooser 监听（按钮触发时用）
  const chooserPromise = page.waitForEvent('filechooser', { timeout: 8000 }).catch(() => null);
  // 策略1：直接对隐藏 input[type=file] 设值
  try {
    const inputs = await page.$$('input[type=file]');
    if (inputs.length) {
      await inputs[0].setInputFiles(imagePaths);
      console.log('[附件] 通过 input 上传', imagePaths.length, '张');
      await page.waitForTimeout(1500);
      return true;
    }
  } catch (e) { console.log('[附件] input 方式失败:', e.message); }
  // 策略2：点附件按钮触发 filechooser
  const sels = ['button[aria-label*="附件"]', 'button[aria-label*="上传"]', 'button[aria-label*="图片"]', '[class*="attachBtn"]', 'button:has-text("附件")', 'button:has-text("上传图片")'];
  for (const s of sels) {
    try {
      const el = page.locator(s).first();
      if (await el.count() > 0) { await el.click({ timeout: 4000, force: true }); break; }
    } catch (_) {}
  }
  const chooser = await chooserPromise;
  if (chooser) {
    await chooser.setFiles(imagePaths);
    console.log('[附件] 通过按钮上传', imagePaths.length, '张');
    await page.waitForTimeout(1500);
    return true;
  }
  console.log('[附件] 未找到上传入口，降级纯文本优化');
  return false;
}

// 定位模型回答：用户消息含唯一标记「=== 本次执行指令 ===」，答案在其后的最后一个气泡
// 不能用"最大文本块"——因为用户消息体巨大（整段 prompt 被粘贴），会误抓整页/用户气泡
async function getAnswerText(page) {
  return await page.evaluate(() => {
    const all = [...document.querySelectorAll('*')];
    const userMark = all.find(el => /=== 本次执行指令 ===/.test(el.innerText || ''));
    let userBubble = userMark;
    while (userBubble && !/message|bubble|chat/i.test(userBubble.className || '') && userBubble.parentElement) userBubble = userBubble.parentElement;
    const bubbles = [...document.querySelectorAll('[class*="message"],[class*="bubble"],[class*="chat-item"]')]
      .filter(el => (el.innerText || '').trim().length > 100);
    let answer = null;
    for (const b of bubbles) {
      if (userBubble && (userBubble.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)) {
        if (!answer || (b.innerText || '').length > (answer.innerText || '').length) answer = b;
      }
    }
    if (!answer) {
      const cands = [...document.querySelectorAll('*')].filter(el => {
        const t = (el.innerText || '').trim();
        return t.length > 100 && /Step 1[：:]/.test(t) && !/=== 本次执行指令 ===/.test(t) && el.getBoundingClientRect().width >= 150;
      });
      cands.sort((a, b) => (b.innerText || '').length - (a.innerText || '').length);
      answer = cands[0];
    }
    return answer ? (answer.innerText || '').trim() : '';
  });
}

async function runOne({ dataFile, promptFile, mode, outFile, images }) {
  const PROMPT = fs.readFileSync(promptFile, 'utf8').trim();
  const DATA = fs.readFileSync(dataFile, 'utf8').trim();
  const modeText = mode === 'copy'
    ? '非全量优化（仅标题 / Description，跳过 Step4 视觉 Prompt）'
    : '全量优化（标题 + Description + 视觉 Prompt ×7 全部输出）';
  const imagePaths = resolveImages(images);
  const msg = PROMPT +
    `\n\n=== 本次执行指令 ===\n优化范围：**${modeText}**。\n\n=== 本次数据 ===\n` + DATA;

  const PROFILE = process.env.QW_PROFILE
    || path.join(os.homedir(), '.workbuddy', 'skills', 'qwen-listing-optimizer', 'cdp-profile-h')
    || 'C:/Users/Administrator.DESKTOP-AHRMISP/WorkBuddy/2026-07-16-11-36-41/qianwen-image-downloader/cdp-profile-h';
  const CHROME = findChrome();
  if (!CHROME) throw new Error('未找到 Chrome，请先安装或配置');

  const ctx = await chromium.launchPersistentContext(PROFILE, {
    executablePath: CHROME, headless: true, viewport: { width: 1366, height: 900 },
    args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'],
  });
  const p = ctx.pages()[0] || await ctx.newPage();
  await p.goto('https://www.qianwen.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(6000);

  // 地域检测（qwen 非大陆地区返回"地区不可用"）
  const regionBlocked = await p.evaluate(() => /地区不可用|not available in your region/i.test(document.body.innerText));
  if (regionBlocked) { await ctx.close(); const e = new Error('QWEN_REGION_BLOCKED'); throw e; }

  // 新对话：确保每条是干净会话（独立窗口，零污染）
  try {
    const nb = p.getByText(/新对话|新建对话|开启新对话/i).first();
    if (await nb.count() > 0) { await nb.click({ timeout: 5000 }); await p.waitForTimeout(2000); }
  } catch (e) {}

  // 切模型到 Qwen3.8-Max
  try {
    const sw = p.getByText(/Qwen3/i).first();
    await sw.click({ force: true, timeout: 8000 });
    await p.waitForTimeout(1500);
    const t = p.getByText(/Qwen3\.8/i).first();
    await t.click({ force: true, timeout: 8000 });
    await p.waitForTimeout(2500);
  } catch (e) { console.log('切模型提示(可能已在该模型):', e.message); }

  // 先上传基材图（若有），再填文本——保证同一条消息一起发送
  let attached = false;
  if (imagePaths.length) {
    try { attached = await uploadAttachments(p, imagePaths); }
    catch (e) { console.log('[附件] 上传异常，降级纯文本:', e.message); }
  }
  const imgNote = attached
    ? `\n\n（已随本消息上传 ${imagePaths.length} 张基材图作为视觉引擎垫图，请基于素材图确定素材映射与 SEO 命名。）`
    : (imagePaths.length ? '\n\n（注：本次基材图未成功上传，视觉引擎基于文字描述生成；实际出图阶段将以基材图作参考图。）' : '');

  // 填入输入框（msg + imgNote）
  const fullMsg = msg + imgNote;
  let filled = false;
  try {
    const ta = p.locator('textarea').first();
    if (await ta.count() > 0) { await ta.click({ timeout: 5000 }); await p.waitForTimeout(300); await ta.fill(fullMsg); filled = true; }
  } catch (e) {}
  if (!filled) {
    try {
      const ce = p.locator('[contenteditable="true"]').first();
      if (await ce.count() > 0) { await ce.click({ timeout: 5000 }); await p.waitForTimeout(300); await ce.fill(fullMsg); filled = true; }
    } catch (e) {}
  }
  if (!filled) { await ctx.close(); throw new Error('未找到输入框'); }
  if (imagePaths.length && !attached) console.log('[附件] 未上传，已注明降级');

  // 发送：优先点击"发送"按钮，回退 Enter（contenteditable 里 Enter 是换行）
  let sent = false;
  try {
    const s = p.locator('button:has-text("发送")').first();
    if (await s.count() > 0) { await s.click({ timeout: 5000 }); sent = true; }
  } catch (e) {}
  if (!sent) { await p.keyboard.press('Enter'); }
  await p.waitForTimeout(2000);

  // 等待生成（轮询"答案气泡"长度稳定）
  let prev = -1, stable = 0;
  const start = Date.now();
  while (Date.now() - start < 180000) {
    await p.waitForTimeout(4000);
    const len = (await getAnswerText(p)).length;
    if (len > 0 && len === prev) { if (++stable >= 2) break; }
    else { stable = 0; prev = len; if (len > 0) console.log('生成中 len=', len); }
  }
  await p.waitForTimeout(3000);

  // 抓取输出（定位用户标记之后的答案气泡）
  const out = await getAnswerText(p);
  if (!out) console.log('[警告] 未抓到模型回答，请检查输出文件');
  fs.writeFileSync(outFile, `===== Qwen3.8-Max 输出 (${mode}) =====\n时间: ${new Date().toISOString()}\n源: ${path.basename(dataFile)}\n\n${out}`, 'utf8');
  console.log('已保存:', outFile, '长度', out.length);
  await ctx.close();
  return out;
}

module.exports = { runOne };

if (require.main === module) {
  const a = parseArgs(process.argv.slice(2));
  if (!a.data || !a.prompt) {
    console.log('用法: node optimize-one.js --data <文件> --prompt <提示词> --mode full|copy --images <基材目录或文件> --out <输出>');
    process.exit(1);
  }
  runOne({ dataFile: a.data, promptFile: a.prompt, mode: a.mode || 'full', outFile: a.out || a.data.replace(/\.[^.]+$/, '-out.md'), images: a.images })
    .then(() => console.log('DONE')).catch(e => {
      if (/REGION_BLOCKED/.test(e.message)) console.error('错误: qianwen.com 显示"地区不可用"，需中国大陆出口 IP');
      else console.error('ERROR:', e.message);
      process.exit(1);
    });
}

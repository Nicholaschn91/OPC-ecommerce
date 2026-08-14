'use strict';
/**
 * lib/browser.js  —  浏览器启动 + 导航 + 登录检测 + 模型回读
 */
const { sleep, BASE_URL, CHROME_EXE, SEL_MODEL_NAME, DEFAULT_PROXY } = require('./constants');

function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_LIB,
    'playwright',
    'C:/Users/nicho/AppData/Local/npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright',
    'C:/Users/nicho/.workbuddy/binaries/node/versions/22.22.2/node_modules/@playwright/cli/node_modules/playwright',
  ].filter(Boolean);
  let lastErr;
  for (const c of candidates) {
    try { return require(c); } catch (e) { lastErr = e; }
  }
  throw new Error('找不到 playwright。设置 PLAYWRIGHT_LIB 环境变量。\n最后错误: ' + (lastErr && lastErr.message));
}

async function launch(browserOpts, log) {
  const { chromium } = loadPlaywright();
  const launchOpts = {
    headless: browserOpts.headless,
    executablePath: CHROME_EXE,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'],
  };
  if (browserOpts.proxy) launchOpts.proxy = { server: browserOpts.proxy };
  const ctx = await chromium.launchPersistentContext(browserOpts.profile, launchOpts);
  const page = ctx.pages()[0] || (await ctx.newPage());
  return { ctx, page };
}

async function openChat(page, model, log) {
  const url = BASE_URL + '?model=' + encodeURIComponent(model);
  log('→ 打开 ' + url);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
}

async function waitStable(page, log) {
  for (let i = 0; i < 6; i++) {
    try {
      await page.waitForLoadState('networkidle', { timeout: 12000 });
      await page.waitForSelector('ms-chat-turn, textarea, ms-model-selector, a, button', { timeout: 12000 });
      return true;
    } catch (e) {
      log('  ⏳ 页面尚未稳定，重试 (' + (5 - i) + ' 剩余)');
      await sleep(2500);
    }
  }
  return false;
}

async function checkLogin(page) {
  for (let i = 0; i < 4; i++) {
    try {
      return await page.evaluate(() =>
        /accounts\.google\.com/.test(location.href) ||
        [...document.querySelectorAll('a, button')].some((e) => /Sign in/i.test(e.textContent || ''))
      );
    } catch (e) {
      await waitStable(page, () => {});
    }
  }
  return false;
}

async function verifyModel(page, expect, log) {
  for (let i = 0; i < 10; i++) {
    const name = await page
      .evaluate((sel) => {
        const el = document.querySelector(sel);
        return el ? (el.textContent || '').trim() : '';
      }, SEL_MODEL_NAME)
      .catch(() => '');
    if (name) return name;
    await sleep(1000);
  }
  return '';
}

async function closeOverlays(page, log) {
  const hasBackdrop = () =>
    page.evaluate((s) => !!document.querySelector(s), require('./constants').SEL_BACKDROP).catch(() => false);
  if (!(await hasBackdrop())) return true;
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press('Escape');
    await sleep(700);
    if (!(await hasBackdrop())) {
      if (log) log('  遮罩层已关闭（Escape ×' + (i + 1) + '）');
      return true;
    }
  }
  return false;
}

/**
 * selectModel — 显式点选目标模型（URL ?model= 参数在 AI Studio 不生效，必须下拉点选）
 * 步骤：开选择器 → 关掉 Upgrade 横幅(Dismiss) → 点含 slug 的文本叶
 */
async function selectModel(page, model, log) {
  await page.click('[data-test-id="model-name"]', { timeout: 5000 }).catch(() => {});
  await sleep(1500);
  // 关掉升级横幅
  const dismissed = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button, [role="button"]')].find(
      (x) => (x.getAttribute('aria-label') || '').trim() === 'Dismiss'
    );
    if (b) { b.click(); return true; }
    return false;
  });
  if (log && dismissed) log('  已关闭 Upgrade 横幅');
  await sleep(1200);
  // 点选匹配模型
  const clicked = await page.evaluate((m) => {
    const leaves = [...document.querySelectorAll('*')].filter(
      (e) => e.children.length === 0 && (e.textContent || '').trim().toLowerCase().includes(m.toLowerCase())
    );
    if (!leaves.length) return false;
    leaves[0].click();
    return true;
  }, model);
  await sleep(1500);
  return clicked;
}

module.exports = { loadPlaywright, launch, openChat, waitStable, checkLogin, verifyModel, closeOverlays, selectModel };

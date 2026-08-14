const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const sleep = ms => new Promise(r => setTimeout(r, ms));
const now = new Date();
const stamp = now.toISOString().replace(/[:T]/g, '-').slice(0, 19);
const OUTDIR = path.join(__dirname, '..', 'outputs');
if (!fs.existsSync(OUTDIR)) fs.mkdirSync(OUTDIR, { recursive: true });
const OUTFILE = path.join(OUTDIR, `test_${stamp}.md`);

// 示例商品信息（结构化输入）
const PRODUCT_INPUT = `产品名称：Custom Photo Night Light for Kids
类目：Home & Garden > Lighting > Night Lights
目标平台：Amazon / eBay / Etsy
核心关键词：personalized night light, custom photo lamp, kids bedside lamp, photo gift, bedroom decor
产品描述：Upload your favorite photo to create a personalized night light. Soft warm LED glow, acrylic panel with UV-printed photo, wooden base, USB powered. Ideal gift for birthdays, anniversaries, baby showers, and holidays.
变体/尺寸：Base finish: light wood / dark wood; Panel size: 6×6 inches / 8×8 inches
设计方向：方向A（套系化视觉方案）`;

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const contexts = browser.contexts();
  let pages = [];
  for (const ctx of contexts) for (const p of ctx.pages()) pages.push(p);
  const page = pages.find(p => /aistudio\.google\.com/.test(p.url())) || pages[0];
  console.log('PAGE', page.url());

  if (!/gemini-3\.1-pro-preview/.test(page.url())) {
    throw new Error('模型不是 gemini-3.1-pro-preview: ' + page.url());
  }

  // 验证 SI 已选
  const siTitle = await page.evaluate(() => {
    const title = document.querySelector('ms-instructions-editor [formcontrolname="title"] input, input[aria-label*="title" i], [data-test-id="instructions-title"]');
    if (title) return title.value;
    const heads = [...document.querySelectorAll('h2,h3,div,span')].filter(e => /POD-印花底稿-v5\.4/.test(e.textContent || ''));
    return heads[0]?.textContent?.trim() || '';
  });
  console.log('SI_TITLE', siTitle || '（通过下拉/面版显示）');

  // 关闭可能打开的 SI 编辑面板/遮罩
  await page.keyboard.press('Escape');
  await sleep(500);

  // 聚焦会话输入框并拟人键入
  const inputSel = 'textarea[placeholder*="Start typing a prompt"]';
  await page.click(inputSel);
  await sleep(300);

  console.log('TYPE_START');
  // 拟人化但加速：20ms/字符（快手速），段间 150ms
  const paragraphs = PRODUCT_INPUT.split('\n');
  for (let i = 0; i < paragraphs.length; i++) {
    await page.keyboard.type(paragraphs[i], { delay: 20 });
    if (i < paragraphs.length - 1) {
      await page.keyboard.press('Shift+Enter');
      await sleep(150);
    }
  }
  console.log('TYPE_END');
  await sleep(300);

  // 点击 Run 发送
  const runBtn = await page.locator('button:has-text("Run")').first();
  await runBtn.click();
  console.log('RUN_CLICKED');

  // 等待生成完成：输出区文本出现且稳定
  let lastLen = 0;
  let stable = 0;
  const start = Date.now();
  let outputText = '';
  while (Date.now() - start < 120000) {
    await sleep(1500);
    const state = await page.evaluate(() => {
      // AI Studio 输出区常见结构
      const out = document.querySelector('[data-test-id="prompt-output-text"], .prompt-output, [contenteditable="true"]');
      const runBtns = [...document.querySelectorAll('button')].filter(b => /run/i.test(b.textContent || ''));
      const stopBtns = [...document.querySelectorAll('button')].filter(b => /stop/i.test(b.textContent || ''));
      return { len: (out?.textContent || '').length, running: stopBtns.length > 0 };
    });
    console.log('WAIT', state.len, 'RUNNING', state.running);
    if (state.len > 0 && !state.running) {
      if (state.len === lastLen) {
        stable++;
        if (stable >= 2) { outputText = 'ready'; break; }
      } else {
        stable = 0;
        lastLen = state.len;
      }
    }
  }

  // 尝试点击 copy as text 按钮
  let copied = '';
  try {
    const copyBtn = page.locator('button:has-text("copy as text"), button[aria-label*="copy" i]').first();
    await copyBtn.click();
    await sleep(800);
    copied = execSync('powershell -NoProfile -Command "Get-Clipboard"', { encoding: 'utf8', maxBuffer: 1024 * 1024 });
    console.log('CLIPBOARD_LEN', copied.length);
  } catch (e) {
    console.log('COPY_BTN_FAIL', e.message);
  }

  // 无论如何用 evaluate 兜底取输出区可见文本
  const evalText = await page.evaluate(() => {
    const out = document.querySelector('[data-test-id="prompt-output-text"], .prompt-output, [contenteditable="true"]');
    return out ? out.innerText : '';
  });

  const finalText = copied || evalText;
  if (!finalText) throw new Error('未取到模型输出');

  const report = `# AI Studio 实测 - ${stamp}

## 输入
\`\`\`
${PRODUCT_INPUT}
\`\`\`

## 输出（${finalText.length} 字符）
\`\`\`
${finalText}
\`\`\`

## 来源
- 模型：gemini-3.1-pro-preview
- 系统指令：POD-印花底稿-v5.4
- 提取方式：${copied ? 'copy as text 按钮 + PowerShell Get-Clipboard' : 'evaluate 兜底取输出区文本'}
`;

  fs.writeFileSync(OUTFILE, report, 'utf8');
  console.log('SAVED', OUTFILE);
  await page.screenshot({ path: path.join(OUTDIR, `test_${stamp}.png`) });
  await browser.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });

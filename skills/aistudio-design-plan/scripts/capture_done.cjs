const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const TEMP = 'C:/Users/nicho/AppData/Local/Temp';
const SKILL_OUT = 'C:/Users/nicho/.workbuddy/skills/multi-agent-sop/aistudio-design-plan/outputs';
if (!fs.existsSync(SKILL_OUT)) fs.mkdirSync(SKILL_OUT, { recursive: true });

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const pages = [];
  for (const ctx of browser.contexts()) for (const p of ctx.pages()) pages.push(p);
  const page = pages.find(p => /aistudio\.google\.com/.test(p.url()));
  console.log('URL', page.url());

  const probe = async () => await page.evaluate(() => {
    const turns = [...document.querySelectorAll('ms-chat-turn')];
    const stopBtns = [...document.querySelectorAll('button')].filter(b => /stop/i.test(b.textContent || '')).length;
    const lastTurn = turns[turns.length - 1];
    // 抓最后 model turn 的纯文本（去掉 thinking 链，只看最终答案）
    const lastText = lastTurn ? (lastTurn.textContent || '').replace(/\s+/g, ' ') : '';
    const copyBtns = [...document.querySelectorAll('button')].filter(b => /copy as text/i.test(b.textContent || '')).length;
    return { turnCount: turns.length, stop: stopBtns > 0, lastTextLen: lastText.length, copyBtns };
  });

  let prev = await probe();
  console.log('START', JSON.stringify(prev));
  let stable = 0;
  const start = Date.now();
  while (Date.now() - start < 180000) {
    await sleep(4000);
    const cur = await probe();
    if (!cur.stop && cur.lastTextLen > 100 && cur.copyBtns > 0) {
      if (cur.lastTextLen === prev.lastTextLen) {
        stable++;
        if (stable >= 3) {
          console.log('COMPLETED', JSON.stringify(cur));
          break;
        }
      } else {
        stable = 0;
      }
    } else {
      stable = 0;
    }
    prev = cur;
  }

  await page.screenshot({ path: path.join(TEMP, 'aistudio_done.png'), fullPage: true });

  // 取最终输出文本（最后一个 turn 的全文，剥掉 thinking）
  const fullText = await page.evaluate(() => {
    const turns = [...document.querySelectorAll('ms-chat-turn')];
    const lastTurn = turns[turns.length - 1];
    if (!lastTurn) return '';
    // 尝试抓 ms-prompt-chunk（模型正文）而非整个 turn（含 thinking）
    const chunks = lastTurn.querySelectorAll('ms-prompt-chunk');
    if (chunks.length > 1) {
      return chunks[chunks.length - 1].textContent;
    }
    return lastTurn.textContent;
  });

  const stamp = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
  const report = `# AI Studio 实测 - ${stamp}

## 输入
\`\`\`
产品名称：Custom Photo Night Light for Kids
类目：Home & Garden > Lighting > Night Lights
目标平台：Amazon / eBay / Etsy
核心关键词：personalized night light, custom photo lamp, kids bedside lamp, photo gift, bedroom decor
产品描述：Upload your favorite photo to create a personalized night light. Soft warm LED glow, acrylic panel with UV-printed photo, wooden base, USB powered. Ideal gift for birthdays, anniversaries, baby showers, and holidays.
变体/尺寸：Base finish: light wood / dark wood; Panel size: 6×6 inches / 8×8 inches
设计方向：方向A（套系化视觉方案）
\`\`\`

## 输出（${fullText.length} 字符）
\`\`\`
${fullText}
\`\`\`

## 提取方式
- 浏览器: 用户 Chrome (CDP 9222)
- 模型: gemini-3.1-pro-preview
- 系统指令: POD-印花底稿-v5.4 (本地缓存命名保存)
- 提取: ms-prompt-chunk 最后 chunk
- 触发: 用户手动点击 "rerun this turn"
`;

  const outFile = path.join(SKILL_OUT, `test_${stamp}.md`);
  fs.writeFileSync(outFile, report, 'utf8');
  console.log('SAVED', outFile);
  console.log('LEN', fullText.length);
  await browser.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
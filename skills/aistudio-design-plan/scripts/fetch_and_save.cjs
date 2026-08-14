const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SKILL_OUT = 'C:/Users/nicho/.workbuddy/skills/multi-agent-sop/aistudio-design-plan/outputs';
if (!fs.existsSync(SKILL_OUT)) fs.mkdirSync(SKILL_OUT, { recursive: true });

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const pages = [];
  for (const ctx of browser.contexts()) for (const p of ctx.pages()) pages.push(p);
  const page = pages.find(p => /aistudio\.google\.com/.test(p.url()));
  console.log('URL', page.url());

  // 先找更宽松的 copy 按钮（在任何位置，包括 icon-only）
  const copyCandidates = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')];
    return btns.map(b => ({
      t: (b.textContent || '').trim().slice(0, 30),
      aria: b.getAttribute('aria-label') || '',
      cls: (b.className || '').slice(0, 80),
      inLastTurn: !!b.closest('ms-chat-turn:last-of-type, ms-chat-turn:nth-last-of-type(1)')
    })).filter(b => /copy/i.test(b.t + ' ' + b.aria));
  });
  console.log('COPY_CANDIDATES', JSON.stringify(copyCandidates, null, 2));

  // 抓最后一个 model turn 的干净 chunk 文本
  const result = await page.evaluate(() => {
    const turns = [...document.querySelectorAll('ms-chat-turn')];
    const lastTurn = turns[turns.length - 1];
    if (!lastTurn) return { ok: false, reason: 'no turn' };
    const chunks = [...lastTurn.querySelectorAll('ms-prompt-chunk')];
    if (chunks.length === 0) return { ok: false, reason: 'no chunk', turnHTML: lastTurn.outerHTML.slice(0, 500) };
    // 取每个 chunk 文本，标记 v5.4 特征
    const chunkData = chunks.map((c, i) => {
      const txt = (c.textContent || '');
      return {
        i, len: txt.length,
        hasOption: /Option \d+:/i.test(txt),
        hasAmazon: /Amazon_VisualBridge/i.test(txt),
        hasEbay: /eBay_VisualBridge/i.test(txt),
        hasEtsy: /Etsy_VisualBridge/i.test(txt),
        head: txt.slice(0, 100),
        tail: txt.slice(-100)
      };
    });
    // 选 answer chunk：含 v5.4 特征的最大 chunk
    const answer = chunkData.find(c => c.hasOption && (c.hasAmazon || c.hasEbay || c.hasEtsy)) || chunkData[chunkData.length - 1];
    const answerText = chunks[answer.i].textContent;
    return { ok: true, chunkData, answerIdx: answer.i, answerLen: answerText.length, answerText };
  });

  if (!result.ok) {
    console.log('FAIL', result.reason);
    await browser.close();
    process.exit(1);
  }

  const stamp = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
  const report = `# AI Studio 实测 - ${stamp} (用户手动 Rerun 后)

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

## 模型 chunk 信息
${JSON.stringify(result.chunkData, null, 2)}

## v5.4 协议最终答案（${result.answerLen} 字符，chunk #${result.answerIdx}）
\`\`\`
${result.answerText}
\`\`\`

## 提取方式
- 浏览器: 用户 Chrome (CDP 9222)
- 模型: gemini-3.1-pro-preview
- 系统指令: POD-印花底稿-v5.4 (本地缓存命名保存)
- 触发: 用户手动点击 "Rerun this turn" → 生成成功
- 抓取: ms-chat-turn 最后 → ms-prompt-chunk 取含 v5.4 特征的最大 chunk
`;

  const outFile = path.join(SKILL_OUT, `test_rerun_${stamp}.md`);
  fs.writeFileSync(outFile, report, 'utf8');
  console.log('SAVED', outFile);
  console.log('ANSWER_LEN', result.answerLen);
  console.log('ANSWER_HEAD', result.answerText.slice(0, 200));

  await browser.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
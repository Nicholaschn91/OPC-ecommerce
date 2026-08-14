const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const pages = [];
  for (const ctx of browser.contexts()) for (const p of ctx.pages()) pages.push(p);
  const page = pages.find(p => /aistudio\.google\.com/.test(p.url()));
  console.log('URL', page.url());

  await page.screenshot({ path: 'C:/Users/nicho/AppData/Local/Temp/aistudio_probe2.png', fullPage: true });

  const info = await page.evaluate(() => {
    const turns = [...document.querySelectorAll('ms-chat-turn')];
    const stopBtns = [...document.querySelectorAll('button')].filter(b => /stop/i.test(b.textContent || '')).length;
    const lastTurn = turns[turns.length - 1];
    const lastTurnClass = lastTurn ? (lastTurn.className || '').slice(0, 100) : '';
    // 列出所有 chunks（model turn 通常含多个 ms-prompt-chunk：thinking + answer）
    const chunks = lastTurn ? [...lastTurn.querySelectorAll('ms-prompt-chunk')] : [];
    const chunkInfo = chunks.map((c, i) => {
      const txt = (c.textContent || '').slice(0, 200).replace(/\s+/g, ' ');
      const cls = (c.className || '').slice(0, 80);
      // 检测是否是 thinking（关键词）
      const thinkingHints = ['Defining', 'Refining', 'Crafting', 'Thinking', 'Analyzing', 'Considering'];
      const isThinking = thinkingHints.some(k => txt.startsWith(k) || /^(I'm|I am|Now|Let me)/.test(txt));
      // 检测是否是 answer（v5.4 协议特征）
      const answerHints = ['Option 1:', 'Amazon_VisualBridge', 'eBay_VisualBridge', 'Etsy_VisualBridge', 'Prompt:', 'Semantic Tags:', 'Core Visual Selling Points:'];
      const isAnswer = answerHints.some(k => txt.includes(k));
      return { i, len: c.textContent.length, cls, head: txt, isThinking, isAnswer };
    });
    // 找 Rerun 按钮
    const rerunBtns = [...document.querySelectorAll('button')].filter(b => /rerun|retry|re-run/i.test((b.textContent || '') + ' ' + (b.getAttribute('aria-label') || ''))).map(b => ({ t: (b.textContent || '').trim().slice(0, 30), aria: b.getAttribute('aria-label'), cls: (b.className || '').slice(0, 60) }));
    // 找 copy as text
    const copyBtns = [...document.querySelectorAll('button')].filter(b => /copy as text|^copy$|copy/i.test((b.textContent || '') + ' ' + (b.getAttribute('aria-label') || ''))).map(b => ({ t: (b.textContent || '').trim().slice(0, 30), aria: b.getAttribute('aria-label') }));
    return { url: location.href, turnCount: turns.length, stop: stopBtns > 0, lastTurnClass, chunkCount: chunks.length, chunkInfo, rerunBtns, copyBtns };
  });
  console.log('INFO', JSON.stringify(info, null, 2));
  fs.writeFileSync('C:/Users/nicho/AppData/Local/Temp/aistudio_probe2.json', JSON.stringify(info, null, 2));
  console.log('SAVED JSON');
  await browser.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
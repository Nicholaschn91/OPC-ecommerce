const { chromium } = require('playwright');
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const pages = [];
  for (const ctx of browser.contexts()) for (const p of ctx.pages()) pages.push(p);
  const page = pages.find(p => /aistudio\.google\.com/.test(p.url()));
  console.log('URL', page.url());
  const state = await page.evaluate(() => {
    const turns = [...document.querySelectorAll('ms-chat-turn')];
    const stop = [...document.querySelectorAll('button')].filter(b => /stop/i.test(b.textContent || '')).length > 0;
    const lastTurn = turns[turns.length - 1];
    const lastText = lastTurn ? (lastTurn.textContent || '').slice(0, 800).replace(/\s+/g, ' ') : '';
    // 显式区分旧/新错误：新错误一定含"0.Xs"等时长在最近 turn 后的错误
    const errorEls = [...document.querySelectorAll('*')].filter(e => /internal error/i.test(e.textContent || '') && e.children.length < 4);
    const errorTexts = errorEls.map(e => e.textContent.trim().slice(0, 100));
    const copyBtns = [...document.querySelectorAll('button')].filter(b => /copy as text/i.test(b.textContent || '')).length;
    return { turnCount: turns.length, stop, lastText, errorCount: errorEls.length, errorTexts, copyBtns };
  });
  console.log('NOW', JSON.stringify(state, null, 2));
  await page.screenshot({ path: 'C:/Users/nicho/AppData/Local/Temp/aistudio_now.png' });
  console.log('SHOT', 'C:/Users/nicho/AppData/Local/Temp/aistudio_now.png');
  await browser.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
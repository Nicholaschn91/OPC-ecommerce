const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const TEMP = 'C:/Users/nicho/AppData/Local/Temp';
const LOG = path.join(TEMP, 'aistudio_monitor_log.json');

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const pages = [];
  for (const ctx of browser.contexts()) for (const p of ctx.pages()) pages.push(p);
  const page = pages.find(p => /aistudio\.google\.com/.test(p.url()));
  if (!page) { console.error('NO_PAGE'); process.exit(1); }
  console.log('URL', page.url());

  const log = [];
  const probe = async () => await page.evaluate(() => {
    const turns = [...document.querySelectorAll('ms-chat-turn')];
    const stop = [...document.querySelectorAll('button')].filter(b => /stop/i.test(b.textContent || '')).length > 0;
    const lastTurn = turns[turns.length - 1];
    const lastText = lastTurn ? (lastTurn.textContent || '').slice(0, 500).replace(/\s+/g, ' ') : '';
    const hasError = [...document.querySelectorAll('*')].filter(e => /internal error/i.test(e.textContent || '') && e.children.length < 4).length > 0;
    return { turnCount: turns.length, stop, lastText, hasError };
  });

  const initial = await probe();
  await page.screenshot({ path: path.join(TEMP, 'aistudio_monitor_initial.png') });
  log.push({ t: Date.now(), phase: 'initial', state: initial });
  console.log('INITIAL', JSON.stringify(initial));

  // 等用户点 Rerun：turnCount 增加或 hasError 变化或 lastText 大幅变化
  let prev = initial;
  let triggered = false;
  const start = Date.now();
  while (Date.now() - start < 90000) {
    await sleep(3000);
    try {
      const cur = await probe();
      const changed = JSON.stringify(cur) !== JSON.stringify(prev);
      if (changed) {
        log.push({ t: Date.now(), phase: 'change', state: cur });
        console.log('CHANGE', JSON.stringify(cur));
        await page.screenshot({ path: path.join(TEMP, `aistudio_monitor_${Date.now()}.png`) });
        prev = cur;
        triggered = true;
      }
      // 完成条件：model turn 有内容 >200 且无 internal error 且不在 stop 状态
      if (cur.lastText.length > 200 && !cur.hasError && !cur.stop) {
        console.log('COMPLETED');
        break;
      }
      // 再次 internal error（用户可能点了 Rerun 但还是失败）
      if (cur.hasError && triggered) {
        console.log('INTERNAL_ERROR_AFTER_RERUN');
        break;
      }
    } catch (e) {
      log.push({ t: Date.now(), phase: 'probe_err', msg: e.message });
    }
  }
  await page.screenshot({ path: path.join(TEMP, 'aistudio_monitor_final.png') });
  fs.writeFileSync(LOG, JSON.stringify(log, null, 2));
  console.log('DONE');
  await browser.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
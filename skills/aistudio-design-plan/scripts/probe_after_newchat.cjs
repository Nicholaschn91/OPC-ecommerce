const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const pages = [];
  for (const ctx of browser.contexts()) for (const p of ctx.pages()) pages.push(p);
  const page = pages.find(p => /aistudio\.google\.com/.test(p.url()));
  console.log('URL', page.url());

  await page.screenshot({ path: 'C:/Users/nicho/AppData/Local/Temp/aistudio_after_newchat.png', fullPage: true });

  const info = await page.evaluate(() => {
    const tas = [...document.querySelectorAll('textarea')].map((t, i) => ({
      i, ph: (t.getAttribute('placeholder') || ''), val: (t.value || '').length
    }));
    const overlays = [...document.querySelectorAll('div, dialog')].filter(d =>
      d.className && /cdk-overlay|mat-mdc-dialog|dialog-backdrop|cdk-overlay-backdrop/i.test(d.className)
    ).slice(0, 5).map(d => d.className.slice(0, 80));
    const exploreModels = [...document.querySelectorAll('*')]
      .filter(e => /explore google models/i.test(e.textContent || '') && e.children.length < 6).length;
    const runBtns = [...document.querySelectorAll('button')].filter(b => /^run\b/i.test(b.textContent || '')).map(b => ({
      t: (b.textContent || '').trim().slice(0, 40),
      disabled: b.disabled,
      cls: (b.className || '').slice(0, 60)
    }));
    const stopBtns = [...document.querySelectorAll('button')].filter(b => /stop/i.test(b.textContent || '')).length;
    const turns = [...document.querySelectorAll('ms-chat-turn')].length;
    const chunks = [...document.querySelectorAll('ms-prompt-chunk')].length;
    const lastTurn = [...document.querySelectorAll('ms-chat-turn')].slice(-1)[0];
    const lastText = lastTurn ? (lastTurn.textContent || '').slice(0, 300).replace(/\s+/g, ' ') : '';
    const url = location.href;
    return { url, textareaCount: tas.length, tas, overlays, exploreModelsCount: exploreModels, runBtns, stopBtns, turnCount: turns, chunkCount: chunks, lastText };
  });
  console.log('INFO', JSON.stringify(info, null, 2));
  await browser.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
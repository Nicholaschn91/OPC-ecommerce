const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const pages = [];
  for (const ctx of browser.contexts()) for (const p of ctx.pages()) pages.push(p);
  const page = pages.find(p => /aistudio\.google\.com/.test(p.url()));
  const info = await page.evaluate(() => {
    const url = location.href;
    const newChatBtns = [...document.querySelectorAll('a, button, [role="link"]')]
      .filter(b => /new chat|新建/i.test((b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')))
      .slice(0, 8).map(b => ({ tag: b.tagName, t: (b.textContent || '').trim().slice(0, 30), aria: b.getAttribute('aria-label'), href: b.getAttribute('href') }));
    return { url, newChatBtns };
  });
  console.log(JSON.stringify(info, null, 2));
  await browser.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
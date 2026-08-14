const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const pages = [];
  for (const ctx of browser.contexts()) for (const p of ctx.pages()) pages.push(p);
  const page = pages.find(p => /aistudio\.google\.com/.test(p.url()));
  console.log('URL', page.url());
  await page.screenshot({ path: 'C:/Users/nicho/AppData/Local/Temp/aistudio_after_run.png', fullPage: true });
  const info = await page.evaluate(() => {
    const sels = ['[data-test-id="prompt-output-text"]', '.prompt-output', '[contenteditable="true"]',
      'ms-prompt-output', 'ms-chat-turn', 'ms-text-content', '[role="textbox"]',
      'div[class*="output"]', 'div[class*="response"]', 'p[class*="model"]', '.model-response',
      'ms-prompt-chunk', '[class*="chunk"]', '[class*="turn"]', '[class*="message"]'];
    const found = sels.map(s => {
      const els = document.querySelectorAll(s);
      return { s, n: els.length, sample: els[0] ? (els[0].textContent || '').slice(0, 100).replace(/\s+/g, ' ') : '' };
    });
    const errs = [...document.querySelectorAll('*')].filter(e => /internal error|something went wrong|try again|unavailable|not available|quota|limit|pro_preview/i.test(e.textContent || '') && e.children.length < 6).slice(0, 8).map(e => ({ tag: e.tagName, t: e.textContent.trim().slice(0, 120) }));
    const url = location.href;
    // 找任何带"copy"或"copy as text"的按钮
    const copyBtns = [...document.querySelectorAll('button')].filter(b => /copy/i.test(b.textContent || '') || /copy/i.test(b.getAttribute('aria-label') || '')).map(b => (b.textContent || '').trim() + '|' + b.getAttribute('aria-label'));
    // Run 按钮状态
    const runBtns = [...document.querySelectorAll('button')].filter(b => /run|stop/i.test(b.textContent || '')).map(b => (b.textContent || '').trim().slice(0, 40));
    return JSON.stringify({ url, found: found.filter(f => f.n > 0), errs, copyBtns, runBtns });
  });
  console.log('INFO', info);
  await browser.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });

const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const contexts = browser.contexts();
  let pages = [];
  for (const ctx of contexts) for (const p of ctx.pages()) pages.push(p);
  const aiPage = pages.find(p => /aistudio\.google\.com/.test(p.url())) || pages[0];
  console.log('FOUND_PAGE', aiPage.url());

  const info = await aiPage.evaluate(() => {
    const tas = [...document.querySelectorAll('textarea')].map((ta, i) => ({
      i, ph: (ta.getAttribute('placeholder') || ''), val: (ta.value || '').length
    }));
    const modelHits = [...document.querySelectorAll('*')]
      .filter(e => /gemini-3\.1-pro-preview|gemini-3|gemini-2|flash/i.test(e.textContent || '') && e.children.length < 4)
      .slice(0, 6).map(e => ({ t: e.textContent.trim().slice(0, 45), tag: e.tagName }));
    const siDropdown = [...document.querySelectorAll('button, mat-select, [role="combobox"]')]
      .filter(b => /POD-印花底稿|system instructions|instruction/i.test(b.textContent || ''))
      .slice(0, 4).map(b => ({ t: (b.textContent || '').trim().slice(0, 45) }));
    const chatInput = document.querySelector('textarea[aria-label*="prompt" i], textarea[placeholder*="message" i], textarea[placeholder*="发送" i], div[contenteditable="true"]');
    const newChat = [...document.querySelectorAll('button,a,[role="button"]')]
      .filter(b => /new chat|new conversation|新建|plus/i.test((b.textContent || '') + (b.getAttribute('aria-label') || '')))
      .slice(0, 6).map(b => ({ t: (b.textContent || '').trim().slice(0, 30), aria: b.getAttribute('aria-label') }));
    const sendBtn = [...document.querySelectorAll('button,[role="button"]')]
      .filter(b => /send|submit|run|生成|发送/i.test((b.textContent || '') + (b.getAttribute('aria-label') || '')))
      .slice(0, 6).map(b => ({ t: (b.textContent || '').trim().slice(0, 30), aria: b.getAttribute('aria-label') }));
    return JSON.stringify({
      url: location.href,
      taCount: tas.length, tas,
      modelHits, siDropdown,
      chatInput: chatInput ? (chatInput.getAttribute('placeholder') || chatInput.className.slice(0, 40)) : null,
      newChat, sendBtn
    });
  });
  console.log('PROBE', info);
  await aiPage.screenshot({ path: 'C:/Users/nicho/AppData/Local/Temp/aistudio_probe.png' });
  console.log('SHOT_OK', 'C:/Users/nicho/AppData/Local/Temp/aistudio_probe.png');
  await browser.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });

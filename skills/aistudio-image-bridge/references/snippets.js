// aistudio-image-bridge — Browser IIFE Snippets
// For use with mcp__browser-aistudio__browser_evaluate when browser_type/browser_press_key aren't sufficient.

// --- Click "Images only" output format ---
const clickImagesOnly = async () => {
  const btn = [...document.querySelectorAll('button')].find(b => (b.textContent||'').includes('Images only'));
  if (!btn) return 'NO_IMAGES_ONLY_BTN';
  btn.click();
  return 'CLICKED';
};

// --- Click "Images & text" output format (for reset) ---
const clickImagesAndText = async () => {
  const btn = [...document.querySelectorAll('button')].find(b => (b.textContent||'').includes('Images & text'));
  if (!btn) return 'NO_IMAGES_TEXT_BTN';
  btn.click();
  return 'CLICKED';
};

// --- Wait for conversation auto-save (URL changes from new_chat to prompts/XXX) ---
const waitForConversationSave = async (timeoutMs = 90000) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (!location.href.includes('new_chat')) return JSON.stringify({saved: true, url: location.href});
    await sleep(2000);
  }
  return JSON.stringify({saved: false, url: location.href, elapsed: Date.now() - start});
};

// --- Click download button on the last generated image ---
const clickDownloadOnGeneratedImage = async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  await sleep(1000);
  const btn = [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === 'download');
  if (!btn) return 'NO_DOWNLOAD_BTN';
  btn.click();
  return JSON.stringify({clicked: true});
};

// --- Get all generated image metadata ---
const getGeneratedImages = () => {
  const imgs = [...document.querySelectorAll('img')].filter(i => i.alt && i.alt.startsWith('Generated Image'));
  return JSON.stringify(imgs.map(i => ({
    alt: i.alt,
    w: i.naturalWidth,
    h: i.naturalHeight,
    srcType: i.src.startsWith('blob:') ? 'blob' : i.src.startsWith('data:') ? 'datauri' : 'other',
    srcLen: i.src.length,
  })));
};

// --- Check if generation is still in progress ---
const isGenerating = () => {
  const bt = document.body.innerText || '';
  return !!/generating|loading|progress/i.test(bt) && !/error/i.test(bt);
};

// Export for use in browser_evaluate function strings:
// To use, reference: clickImagesOnly, waitForConversationSave, clickDownloadOnGeneratedImage, etc.

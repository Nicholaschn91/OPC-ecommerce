// render-preview.js — 把单张 PNG/WebP render 成 720px 宽预览 PNG（本环境无 magick/PIL 时用于核验）
// 用法: node render-preview.js <input.png> [output.png]
// 依赖: playwright-core（NODE_PATH 指向 qianwen-image-downloader/scripts/node_modules）
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

(async () => {
  const inp = process.argv[2];
  if (!inp) { console.error('usage: node render-preview.js <input> [output]'); process.exit(1); }
  const out = process.argv[3] || (path.dirname(inp) + '/' + path.basename(inp, path.extname(inp)) + '.preview.png');
  const b64 = fs.readFileSync(inp).toString('base64');
  const ext = path.extname(inp).slice(1).toLowerCase();
  const mime = ext === 'webp' ? 'image/webp' : 'image/png';
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 760, height: 760 } });
  await page.setContent(`<body style="margin:0;background:#222;display:flex;align-items:center;justify-content:center;min-height:100vh">
    <img src="data:${mime};base64,${b64}" style="max-width:720px;max-height:720px;width:auto;height:auto">
  </body>`);
  const img = await page.$('img');
  await img.screenshot({ path: out });
  await browser.close();
  console.log('preview ->', out, fs.statSync(out).size, 'bytes');
})();

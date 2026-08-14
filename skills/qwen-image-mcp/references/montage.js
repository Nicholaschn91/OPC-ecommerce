// montage.js — 把目录里 *_vN.png 变体拼成 2x2 预览 PNG（核验多张变体）
// 用法: node montage.js <dir> [output.png]
// 依赖: playwright-core（NODE_PATH 指向 qianwen-image-downloader/scripts/node_modules）
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

(async () => {
  const dir = process.argv[2];
  const out = process.argv[3] || (dir + '/montage.png');
  if (!dir) { console.error('usage: node montage.js <dir> [output]'); process.exit(1); }
  const files = fs.readdirSync(dir)
    .filter(f => /_v\d+\.png$/.test(f) && !f.endsWith('.preview.png'))
    .sort()
    .map(f => path.join(dir, f))
    .slice(0, 4);
  if (files.length === 0) { console.error('no *_vN.png found in', dir); process.exit(1); }

  const cells = files.map(f => {
    const b64 = fs.readFileSync(f).toString('base64');
    return `<div class="cell"><img src="data:image/png;base64,${b64}"></div>`;
  }).join('');

  const cell = 360, gap = 12, pad = 12;
  const cols = 2, rows = Math.ceil(files.length / cols);
  const W = pad * 2 + cols * cell + (cols - 1) * gap;
  const H = pad * 2 + rows * cell + (rows - 1) * gap;

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: W, height: H } });
  await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>
    body{margin:0;background:#fff}
    .grid{display:grid;grid-template-columns:repeat(${cols},${cell}px);gap:${gap}px;padding:${pad}px}
    .cell{width:${cell}px;height:${cell}px;overflow:hidden;border:1px solid #ddd;background:#f5f5f5}
    .cell img{width:100%;height:100%;object-fit:cover}
  </style></head><body><div class="grid">${cells}</div></body></html>`);
  await page.screenshot({ path: out, fullPage: true });
  await browser.close();
  console.log('montage ->', out, fs.statSync(out).size, 'bytes');
})();

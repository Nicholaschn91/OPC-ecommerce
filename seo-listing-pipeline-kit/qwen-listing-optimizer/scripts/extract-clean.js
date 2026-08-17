#!/usr/bin/env node
'use strict';
// extract-clean.js v3 — 从 out.md + 源文件产出 data.csv（仅 CSV，舍弃 clean.md）
// 结构化上架数据：title/description/tags/images/alt_text 等 15 列
// alt_text = 分号分隔，整格引号包裹；images 与 alt_text 严格 1:1 同序
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const getArg = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i+1] : null; };
const outFile = getArg('--out');
const sourceFile = getArg('--source');
const dir = getArg('--dir') || path.dirname(outFile || sourceFile || '.');
const csvFile = getArg('--csv') || (outFile ? outFile.replace(/\.md$/, '-data.csv') : null);

if (!outFile || !sourceFile) { console.log('用法: node extract-clean.js --out <out.md> --source <源.txt> --dir <素材目录> [--csv <data.csv>]'); process.exit(1); }

const out = fs.readFileSync(outFile, 'utf8');
const source = fs.readFileSync(sourceFile, 'utf8');
const lines = out.split('\n');

// ====== 源文件解析 ======
function parseSource(text) {
  const r = { alt: [], tags: [], title: '', price: '', materials: '', images: [], sourceImages: [] };
  // Alt（表头兼容 Alt / Alt： 全角冒号等多种写法）
  const as = text.search(/\n\s*Alt\s*[:：]?\s*\n/i);
  if (as >= 0) { for (const l of text.slice(as).split('\n')) { const m = l.match(/^\s*(\d+)\.(.+)/); if (m) r.alt.push(m[2].trim()); } }
  // Tags: stop at Alt boundary（同样兼容全角冒号）
  const ts = text.search(/\n\s*Tag\s*\n/i);
  if (ts >= 0) {
    const ae = text.search(/\n\s*Alt\s*[:：]?\s*\n/i);
    const te = (ae >= 0 && ae > ts) ? ae : text.length;
    for (const l of text.slice(ts, te).split('\n')) { const t = l.trim(); if (t && !/^(Tag|Alt)\s*[:：]?$/i.test(t)) r.tags.push(t); }
  }
  // Title
  const tm = text.match(/^Title\s*\n\s*\n(.+)/im);
  if (tm) r.title = tm[1].trim();
  // Price
  const pm = text.match(/\(\w+\)\s*\$?([\d.]+)/);
  if (pm) r.price = pm[1];
  // Materials: 优先抓源文件显式 Material(s): 行；回退只扫 Description 段（不含 Alt/Tags），避免场景词误判
  const matLine = text.match(/^\s*-?\s*Material[s]?\s*[:：]\s*(.+)$/im);
  if (matLine) {
    r.materials = matLine[1].trim().replace(/\s+/g, ' ');
  } else {
    const ds = text.search(/\n\s*Description\s*\n/i);
    const ts = text.search(/\n\s*Tag\s*\n/i);
    if (ds >= 0) {
      const dsec = (ts > ds ? text.slice(ds, ts) : text.slice(ds)).toLowerCase();
      const mats = [];
      if (/leather|牛皮|真皮|疯马皮/i.test(dsec)) mats.push('Leather');
      if (/\bwood|木|birch/i.test(dsec)) mats.push('Wood');
      if (/canvas|帆布/i.test(dsec)) mats.push('Canvas');
      r.materials = mats.join(';') || '';
    }
  }
  // Images: scan dir
  if (fs.existsSync(dir)) {
    r.images = fs.readdirSync(dir).filter(f => /\.(jpg|jpeg|png|webp)$/i.test(f) && !/clean|out|qr|diag|test|data/i.test(f)).sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
    // Pad alt to match image count
    while (r.alt.length < r.images.length) r.alt.push('');
    r.alt = r.alt.slice(0, Math.max(r.images.length, r.alt.length));
  }
  return r;
}

// ====== 从模型输出「📋原始素材摘要」提取 alt / tags ======
// 模型已把输入规范归一化（alt 逐行列出、tags 逗号分隔），从此处取可免疫源文件格式脏乱
// （如 Alt：全角冒号、tags 错贴到 Alt 区后等）。作为 alt/tags 的主取源，源解析作兜底。
function parseModelSummary(text) {
  const r = { alt: [], tags: [] };
  const altHeader = text.search(/图片\s*Alt\s*文本\s*[（(]原始输入[)）]\s*[:：]/);
  const tagsHeader = text.search(/Etsy\s*Tags\s*原始列表\s*[:：]/);
  if (altHeader >= 0 && tagsHeader > altHeader) {
    for (const l of text.slice(altHeader, tagsHeader).split('\n')) {
      const t = l.trim();
      if (t && !/图片|Alt|原始输入/.test(t) && !/^\d+[\.、]/.test(t)) r.alt.push(t);
    }
  }
  if (tagsHeader >= 0) {
    let buf = [];
    for (const l of text.slice(tagsHeader).split('\n')) {
      const t = l.trim();
      if (/Etsy\s*Tags\s*原始列表/.test(t)) continue;
      if (/^(Step|⚙️|⏰|💡|表格|下载|导出|📋)/.test(t)) break;
      if (t) buf.push(t);
    }
    r.tags = buf.join(',').split(',').map(s => s.trim()).filter(s => s && !/^Etsy/i.test(s));
  }
  return r;
}

const sf = parseSource(source);
const ms = parseModelSummary(out);

// ====== 从模型输出提取 title ======
function extractTitle(text) {
  const st1 = text.indexOf('Step 1');
  if (st1 < 0) return '';
  const section = text.slice(st1);
  // 找推荐标题后的第一行纯英文（跳过标记行）
  const m = section.match(/推荐标题.*?\n[^\n]*?\n([\s\S]*?)(?=\n\n|\n🔍|\n表格)/i);
  if (m && m[1]) {
    const candidates = m[1].split('\n').map(l => l.trim()).filter(l => l && !/^(text|编辑|片段|下载|导出|\d+$)/i.test(l) && l.length > 10);
    if (candidates.length) return candidates[0];
  }
  for (const l of section.split('\n')) { const t = l.trim(); if (/^[A-Z]/.test(t) && t.length > 30 && !/Step|表格|下载|导出|text|编辑|片段/.test(t) && !/^\d+$/.test(t)) return t; }
  return sf.title || '';
}

// ====== 从模型输出提取 description（Step 3 区段，清理标记） ======
// 边界必须用全角冒号形式：执行区标题为 `Step 3：纯英文 Description` / `Step 4：...` / `Step 5：...`，
// 而收尾总结句「…将 Step 1 标题与 Step 3 Description 直接上架（Step 4）…」虽含 "Step 3"/"Step 4" 但无冒号，
// 用带冒号的精确匹配可区分执行标题与总结引用，避免 lastIndexOf('Step 3') 误命中总结句被紧邻的（Step 4）截断。
function extractDescription(text) {
  const st3 = text.lastIndexOf('Step 3：');
  if (st3 < 0) return '';
  const st4 = text.indexOf('Step 4：', st3);
  const st5 = text.indexOf('Step 5：', st3);
  let end = text.length;
  if (st4 >= 0) end = Math.min(end, st4);
  if (st5 >= 0) end = Math.min(end, st5);
  const raw = text.slice(st3, end);
  const clean = raw.split('\n').map(l => {
    let t = l.trim();
    if (/^(text|编辑|片段|下载|导出|表格|\d{1,2}\s*$)/i.test(t)) return null;
    t = t.replace(/^\d{1,2}\s+/, '');
    return t;
  }).filter(l => l !== null).join('\n').trim();
  return clean.replace(/^Step\s+3[：:].*?\n+/i, '').replace(/^\s+/, '');
}

const title = extractTitle(lines.join('\n'));
const description = extractDescription(lines.join('\n'));

// alt / tags：模型输出「原始素材摘要」优先（已归一化），源解析兜底
const altSrc = (ms.alt.length > 0 && ms.alt.length === sf.images.length) ? ms.alt : sf.alt;
const tags = (ms.tags.length > 0 ? ms.tags : sf.tags).join(';');

// images & alt_text: 1:1 对应，分号分隔，alt 整格双引号包裹
const images = sf.images.join(';');
let altPadded = altSrc.slice();
while (altPadded.length < sf.images.length) altPadded.push('');
altPadded = altPadded.slice(0, sf.images.length);
const altText = altPadded.map(a => a.replace(/;/g, '，')).join(';'); // 防 alt 内含分号：临时替换为中文逗号

// ====== 产出 CSV ======
const csvEscape = (v) => { const s = String(v||''); return /[",;\n]/.test(s) ? '"' + s.replace(/"/g,'""') + '"' : s; };
const altCell = altText ? csvEscape(altText) : '';

const csvHeader = 'title,description,tags,price_usd,materials,category,who_made,when_made,processing_days,quantity,images,alt_text,variation_axis,variation_values,personalization';
const defaults = { price_usd: sf.price || '', materials: sf.materials || '', category: '', who_made: 'i_did', when_made: 'made_to_order', processing_days: '3-5', quantity: '8', variation_axis: '', variation_values: '', personalization: '' };
const row = [title, description, tags, defaults.price_usd, defaults.materials, defaults.category, defaults.who_made, defaults.when_made, defaults.processing_days, defaults.quantity, images, altCell, defaults.variation_axis, defaults.variation_values, defaults.personalization];

if (csvFile) {
  fs.writeFileSync(csvFile, csvHeader + '\n' + row.map(v => csvEscape(v)).join(',') + '\n', 'utf8');
  const tl = title.length, dl = description.length;
  console.log('data.csv:', csvFile);
  console.log('  title:', tl, 'chars' + (tl ? ' ✅' : ' ⚠️ 空(千问未响应)'));
  console.log('  desc:', dl, 'chars' + (dl ? ' ✅' : ' ⚠️ 空(千问未响应)'));
  console.log('  tags:', (ms.tags.length > 0 ? ms.tags : sf.tags).length, '| imgs:', sf.images.length, '| alt:', altPadded.filter(x=>x).length);
}

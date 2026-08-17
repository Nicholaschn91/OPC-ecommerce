#!/usr/bin/env node
'use strict';
// 批量 listing 优化：循环调用 optimize-one，每条独立新建对话窗口（零污染），分别落盘
const fs = require('fs');
const path = require('path');
const { runOne } = require('./optimize-one');

function parseArgs(argv) {
  const o = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      const k = argv[i].slice(2);
      const v = (argv[i + 1] && !argv[i + 1].startsWith('--')) ? argv[++i] : true;
      o[k] = v;
    }
  }
  return o;
}

(async () => {
  const a = parseArgs(process.argv.slice(2));
  const dir = a.dir, prompt = a.prompt, mode = a.mode || 'full';
  if (!dir || !prompt) {
    console.log('用法: node optimize-batch.js --dir <数据目录> --prompt <提示词> --mode full|copy');
    process.exit(1);
  }
  if (!fs.existsSync(dir)) { console.error('目录不存在:', dir); process.exit(1); }

  const files = fs.readdirSync(dir)
    .filter(f => /\.(md|txt|json|yaml|yml)$/i.test(f))
    .map(f => path.join(dir, f))
    .sort();
  console.log(`批量: ${files.length} 个文件, 模式=${mode}, 每条独立新窗口`);

  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    const out = f.replace(/\.[^.]+$/, '-out.md');
    console.log(`\n[${i + 1}/${files.length}] ${path.basename(f)}`);
    try {
      await runOne({ dataFile: f, promptFile: prompt, mode, outFile: out });
    } catch (e) {
      if (/REGION_BLOCKED/.test(e.message)) {
        console.error('地域限制，终止批量（需中国大陆出口 IP）');
        process.exit(2);
      }
      console.error('  失败:', e.message);
    }
  }
  console.log('\n批量完成');
})();

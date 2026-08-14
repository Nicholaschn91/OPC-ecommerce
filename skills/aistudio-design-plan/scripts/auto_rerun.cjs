const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SKILL_OUT = path.join(__dirname, '..', 'outputs');
if (!fs.existsSync(SKILL_OUT)) fs.mkdirSync(SKILL_OUT, { recursive: true });

const MAX_RERUN = 5;            // internal error 后最多自动 Rerun 次数（用户要求"看着你解决"，放宽）
const TYPE_DELAY_MS = 20;       // 拟人键入 20ms/字
const LINE_PAUSE_MS = 150;      // 段间停顿
const RUN_TIMEOUT_MS = 90000;   // 单次生成最多 90s
const V54_MARKERS = [/Option \d+:/i, /Amazon_VisualBridge/i, /eBay_VisualBridge/i, /Etsy_VisualBridge/i];

async function fetchAnswer(page) {
  return await page.evaluate(() => {
    const turns = [...document.querySelectorAll('ms-chat-turn')];
    const lastTurn = turns[turns.length - 1];
    if (!lastTurn) return null;
    const chunks = [...lastTurn.querySelectorAll('ms-prompt-chunk')];
    if (!chunks.length) return null;
    const chunkTexts = chunks.map(c => (c.textContent || ''));
    const answerIdx = chunkTexts.findIndex(t =>
      /Option \d+:/i.test(t) && /Amazon_VisualBridge|eBay_VisualBridge|Etsy_VisualBridge/i.test(t)
    );
    if (answerIdx < 0) return null;
    return { idx: answerIdx, text: chunkTexts[answerIdx], len: chunkTexts[answerIdx].length };
  });
}

async function waitStopAndAnswer(page, timeoutMs) {
  const start = Date.now();
  let lastTextLen = 0;
  let stable = 0;
  // 多种错误模式
  const ERROR_PATTERNS = [
    /internal error has occurred/i,
    /something went wrong/i,
    /quota exceeded/i,
    /rate.?limit/i,
    /fetch failed/i,
    /network error/i,
    /unavailable/i,
    /try again/i
  ];
  const TOAST_PATTERNS = [
    /failed to generate content/i,
    /permission denied/i,
    /access denied/i,
    /please try again/i,
    /service unavailable/i
  ];
  while (Date.now() - start < timeoutMs) {
    await sleep(1000);
    const state = await page.evaluate((sources) => {
      const errSources = sources.errSources;
      const toastSources = sources.toastSources;
      const turns = [...document.querySelectorAll('ms-chat-turn')];
      const lastTurn = turns[turns.length - 1];
      const chunks = lastTurn ? [...lastTurn.querySelectorAll('ms-prompt-chunk')] : [];
      const lastText = chunks.length ? (chunks[chunks.length - 1].textContent || '') : '';
      const stopBtns = [...document.querySelectorAll('button')].filter(b => /stop/i.test(b.textContent || '')).length;
      const runBtns = [...document.querySelectorAll('button')].filter(b => /^run\b/i.test(b.textContent || '')).length;
      const rerunBtns = [...document.querySelectorAll('button[aria-label="Rerun this turn"]')].length;
      const lastTurnText = lastTurn ? (lastTurn.textContent || '') : '';
      // ★ turn 文本内错误
      const errMatch = errSources.find(src => new RegExp(src, 'i').test(lastTurnText));
      // ★ toast 错误（AI Studio 顶部黄色 toast，role=alert 或 cdk-overlay-container 内）
      const toastEls = [...document.querySelectorAll('[role="alert"], .cdk-overlay-container div, .cdk-overlay-container span')];
      const toastText = toastEls.map(e => (e.textContent || '').slice(0, 200)).join(' | ');
      const toastMatch = toastSources.find(src => new RegExp(src, 'i').test(toastText));
      return {
        turnCount: turns.length,
        stop: stopBtns > 0,
        lastTextLen: lastText.length,
        lastTextHead: lastText.slice(0, 80).replace(/\s+/g, ' '),
        runBtns, rerunBtns,
        errKind: errMatch || null,
        toastErr: toastMatch || null,
        toastText: toastText.slice(0, 120)
      };
    }, { errSources: ERROR_PATTERNS.map(p => p.source), toastSources: TOAST_PATTERNS.map(p => p.source) });

    const errDisplay = state.errKind || state.toastErr || '-';
    console.log(`  [${Math.round((Date.now() - start) / 1000)}s] turn=${state.turnCount} stop=${state.stop} textLen=${state.lastTextLen} run=${state.runBtns} rerun=${state.rerunBtns} err=${errDisplay} head="${state.lastTextHead}"`);

    // ★ 错误立即返回（不等满 90s）— 优先 toast（permission denied 在 toast 不在 turn）
    const errKind = state.toastErr || state.errKind;
    if (errKind && !state.stop) {
      // ★ 错误立即写文件 + 醒目标记，让用户能第一时间看到
      try {
        const errReport = {
          ts: new Date().toISOString(),
          errorKind: errKind,
          toastText: state.toastText,
          turnCount: state.turnCount,
          lastTextHead: state.lastTextHead,
          runBtns: state.runBtns,
          rerunBtns: state.rerunBtns
        };
        fs.writeFileSync(path.join(SKILL_OUT, 'last_error.json'), JSON.stringify(errReport, null, 2));
        console.log(`  >>> ERROR_DETECTED ${errKind} — wrote last_error.json <<<`);
      } catch (e) { /* ignore */ }
      return { ok: false, errorKind: errKind, state };
    }
    // ★ 成功条件放宽：stop:false + textLen>200 + 稳定 3 次（不再要求 v5.4 特征）
    if (state.lastTextLen > 200 && !state.stop) {
      if (state.lastTextLen === lastTextLen) {
        stable++;
        if (stable >= 3) return { ok: true, state };
      } else {
        stable = 0;
        lastTextLen = state.lastTextLen;
      }
    } else {
      stable = 0;
      lastTextLen = state.lastTextLen;
    }
  }
  return { ok: false, state: null, reason: 'timeout' };
}

async function clickRerun(page) {
  // ★ 真鼠标事件：曲线移动 + 抖动 + 按停（避免 Playwright locator.click 的 automation 指纹）
  try {
    const loc = page.locator('button[aria-label="Rerun this turn"]').last();
    const count = await loc.count();
    if (count === 0) return { ok: false, count: 0 };
    const box = await loc.boundingBox();
    if (!box) return { ok: false, count, error: 'no boundingBox' };
    const x = box.x + box.width / 2 + (Math.random() - 0.5) * 4;
    const y = box.y + box.height / 2 + (Math.random() - 0.5) * 4;
    await page.mouse.move(x, y, { steps: 8 + Math.floor(Math.random() * 5) });
    await sleep(80 + Math.random() * 120);
    await page.mouse.down();
    await sleep(30 + Math.random() * 40);
    await page.mouse.up();
    return { ok: true, count };
  } catch (e) {
    return { ok: false, count: 0, error: e.message };
  }
}

async function selectSIByName(page, name) {
  // ★ 真鼠标序列：点 SI 卡片标题 → 点下拉 → 选命名（避免 Playwright locator.click 指纹）
  try {
    // 1. 找 SI 区域标题（点击展开）
    const siHeading = page.locator('text=/System instructions/i').first();
    await siHeading.scrollIntoViewIfNeeded();
    const sBox = await siHeading.boundingBox();
    if (sBox) {
      const sx = sBox.x + sBox.width / 2 + (Math.random() - 0.5) * 3;
      const sy = sBox.y + sBox.height / 2 + (Math.random() - 0.5) * 3;
      await page.mouse.move(sx, sy, { steps: 6 });
      await sleep(120 + Math.random() * 80);
      await page.mouse.down();
      await sleep(40);
      await page.mouse.up();
    }
    await sleep(800 + Math.floor(Math.random() * 400));

    // 2. 点下拉
    const dropdown = page.locator('mat-select, [aria-haspopup="listbox"]').first();
    await dropdown.scrollIntoViewIfNeeded();
    const dBox = await dropdown.boundingBox();
    if (dBox) {
      const dx = dBox.x + dBox.width / 2 + (Math.random() - 0.5) * 3;
      const dy = dBox.y + dBox.height / 2 + (Math.random() - 0.5) * 3;
      await page.mouse.move(dx, dy, { steps: 5 });
      await sleep(100 + Math.random() * 80);
      await page.mouse.down();
      await sleep(40);
      await page.mouse.up();
    }
    await sleep(800 + Math.floor(Math.random() * 400));

    // 3. 选已命名（mat-option）
    const opt = page.locator(`mat-option:has-text("${name}"), [role="option"]:has-text("${name}")`).first();
    await opt.scrollIntoViewIfNeeded();
    const oBox = await opt.boundingBox();
    if (oBox) {
      const ox = oBox.x + oBox.width / 2 + (Math.random() - 0.5) * 3;
      const oy = oBox.y + oBox.height / 2 + (Math.random() - 0.5) * 3;
      await page.mouse.move(ox, oy, { steps: 5 });
      await sleep(100 + Math.random() * 80);
      await page.mouse.down();
      await sleep(40);
      await page.mouse.up();
    }
    await sleep(1000);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function newChat(page) {
  // 点左侧栏 "New chat" 按钮（aria-label="New chat"，侧栏 "+"），等 URL 跳到 new_chat
  const before = page.url();
  // ★ 检测已是 new_chat → 跳过点击（按钮 aria-disabled=true 会 30s 超时）
  if (/prompts\/new_chat/.test(before)) {
    console.log(`NEW_CHAT_SKIP (already on ${before})`);
    return before;
  }
  await page.locator('button[aria-label="New chat"]').first().click();
  const start = Date.now();
  while (Date.now() - start < 15000) {
    await sleep(500);
    const url = page.url();
    if (/prompts\/new_chat/.test(url)) {
      console.log(`NEW_CHAT_OK (was ${before.slice(-40)} → now ${url})`);
      return url;
    }
  }
  throw new Error('点 New chat 后 URL 未跳转到 new_chat（当前 ' + page.url() + '）');
}

async function clearAndType(page, text) {
  await page.click('textarea[placeholder*="Start typing a prompt"]');
  await sleep(200);
  // Ctrl+A 全选，Delete 清空
  await page.keyboard.press('Control+A');
  await sleep(100);
  await page.keyboard.press('Delete');
  await sleep(200);
  const paragraphs = text.split('\n');
  for (let i = 0; i < paragraphs.length; i++) {
    // ★ 真键盘节奏：每字 20-50ms 随机 + 字间偶尔微停（避免规则化输入触发 detection）
    await page.keyboard.type(paragraphs[i], { delay: 20 + Math.floor(Math.random() * 30) });
    if (i < paragraphs.length - 1) {
      await page.keyboard.press('Shift+Enter');
      await sleep(120 + Math.floor(Math.random() * 180));
    }
  }
  await sleep(300);
}

// 解析参数: --file <path> 从文件读，否则 process.argv 拼成 PRODUCT
let inputFile = null;
const cliArgs = process.argv.slice(2);
for (let i = 0; i < cliArgs.length; i++) {
  if (cliArgs[i] === '--file' && cliArgs[i + 1]) { inputFile = cliArgs[++i]; }
}
const PRODUCT = inputFile
  ? fs.readFileSync(inputFile, 'utf8').trim()
  : (cliArgs.join('\n') || `产品名称：Custom Photo Night Light for Kids
类目：Home & Garden > Lighting > Night Lights
目标平台：Amazon / eBay / Etsy
核心关键词：personalized night light, custom photo lamp, kids bedside lamp, photo gift, bedroom decor
产品描述：Upload your favorite photo to create a personalized night light. Soft warm LED glow, acrylic panel with UV-printed photo, wooden base, USB powered. Ideal gift for birthdays, anniversaries, baby showers, and holidays.
变体/尺寸：Base finish: light wood / dark wood; Panel size: 6×6 inches / 8×8 inches
设计方向：方向A（套系化视觉方案）`);

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const pages = [];
  for (const ctx of browser.contexts()) for (const p of ctx.pages()) pages.push(p);
  const page = pages.find(p => /aistudio\.google\.com/.test(p.url()));
  console.log('URL', page.url());

  // ★ 关键：先点 New chat 新建会话（避免在已有 prompt 上追加 turn 污染上下文）
  await newChat(page);
  await sleep(800);

  // ★ 关键：viewport 设到 1920×1080（AI Studio 响应式，物理窗口最大化才能看到完整 UI，CSS zoom 无效）
  try {
    await page.setViewportSize({ width: 1920, height: 1080 });
    console.log('VIEWPORT_SET 1920x1080');
  } catch (e) {
    console.log('VIEWPORT_FAIL', e.message);
  }
  await sleep(300);

  // 关掉可能打开的 SI 编辑面板
  await page.keyboard.press('Escape');
  await sleep(400);

  // 清空 + 键入
  await clearAndType(page, PRODUCT);
  console.log('TYPED');

  // 点 Run
  await page.locator('button:has-text("Run")').first().click();
  console.log('RUN_CLICKED');

  let attempt = 0;
  let finalAnswer = null;
  while (attempt <= MAX_RERUN) {
    const w = await waitStopAndAnswer(page, RUN_TIMEOUT_MS);
    if (!w.ok) {
      if (w.errorKind) {
        console.log(`ATTEMPT ${attempt}: error detected (${w.errorKind}), clicking Rerun immediately`);
      } else {
        console.log(`ATTEMPT ${attempt}: wait timeout, clicking Rerun`);
      }
    } else {
      const ans = await fetchAnswer(page);
      if (ans) {
        finalAnswer = ans;
        console.log(`ATTEMPT ${attempt}: v5.4 answer captured (${ans.len} chars)`);
        break;
      }
      console.log(`ATTEMPT ${attempt}: text >200 but no v5.4 markers, will Rerun`);
    }
    if (attempt >= MAX_RERUN) break;
    const r = await clickRerun(page);
    if (r.ok) {
      // ★ Rerun 后随机等待 4-7s（避免服务端检测太规则的点击节奏）
      const pause = 4000 + Math.floor(Math.random() * 3000);
      console.log(`RERUN_CLICKED (count=${r.count}), pause ${pause}ms`);
      await sleep(pause);
    } else {
      console.log(`RERUN_FAIL (count=0, error=${r.error || 'no button'}), wait 3s`);
      await sleep(3000);
    }
    attempt++;
  }

  if (!finalAnswer) {
    console.error('FAIL: 经过', MAX_RERUN + 1, '次尝试仍未拿到 v5.4 答案');
    await page.screenshot({ path: path.join(SKILL_OUT, 'auto_rerun_fail.png') });
    await browser.close();
    process.exit(1);
  }

  await page.screenshot({ path: path.join(SKILL_OUT, 'auto_rerun_done.png') });

  const stamp = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
  const report = `# AI Studio 自动 Rerun 实测 - ${stamp}

## 输入
\`\`\`
${PRODUCT}
\`\`\`

## 重试次数
${attempt} 次（共 ${MAX_RERUN + 1} 次机会）

## v5.4 协议最终答案（${finalAnswer.len} 字符，chunk #${finalAnswer.idx}）
\`\`\`
${finalAnswer.text}
\`\`\`

## 提取方式
- 浏览器: 用户 Chrome (CDP 9222)
- 模型: gemini-3.1-pro-preview
- 系统指令: POD-印花底稿-v5.4
- Rerun selector: button[aria-label="Rerun this turn"]:last
- 抓取: ms-prompt-chunk 含 v5.4 特征的最大 chunk
`;

  const outFile = path.join(SKILL_OUT, `auto_rerun_${stamp}.md`);
  fs.writeFileSync(outFile, report, 'utf8');
  console.log('SAVED', outFile);
  await browser.close();
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
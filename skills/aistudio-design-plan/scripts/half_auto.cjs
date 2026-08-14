// half_auto.cjs v4 — 半自动协作：脚本只探针/输入/Run/监控/抓取
// 用户明确要求 (8-14 05:38):
//   1) 视口: 真实最大化浏览器窗口 (CDP Browser.setWindowBounds), 不是 setViewportSize
//   2) SI 30s 等待循环删除: SI 切换由用户负责, 脚本只探针一次
//   3) SI 关编辑面板: 由用户在浏览器里自己关, 脚本不做 Esc/blur/click
//   4) Ctrl+Enter 兜底 click Run 按钮删除: 改为停止等待, 等用户处理
//   5) 任何"自动补救"都去掉, 错了就停
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SKILL_OUT = path.join(__dirname, '..', 'outputs');
if (!fs.existsSync(SKILL_OUT)) fs.mkdirSync(SKILL_OUT, { recursive: true });

// 参数解析
const args = process.argv.slice(2);
let inputFile = null;
let httpPort = 8127;
let recordId = 'unknown';
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--file' && args[i + 1]) { inputFile = args[++i]; recordId = path.basename(inputFile).replace(/^input_/, '').replace(/\.txt$/, ''); }
  if (args[i] === '--port' && args[i + 1]) { httpPort = parseInt(args[++i]); }
}
if (!inputFile) { console.error('ERROR: need --file <input.txt>'); process.exit(1); }
const PRODUCT = fs.readFileSync(inputFile, 'utf8').trim();

// 内部 HTTP server 只 serve input
const server = require('http').createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8', 'Access-Control-Allow-Origin': '*' });
  if (req.url === '/input') res.end(PRODUCT);
  else res.end();
}).listen(httpPort, '127.0.0.1', () => console.log(`HTTP READY :${httpPort}`));

// 探针函数
async function probeState(page) {
  return await page.evaluate(() => {
    const turns = [...document.querySelectorAll('ms-chat-turn')];
    const lastTurn = turns[turns.length - 1];
    const chunks = lastTurn ? [...lastTurn.querySelectorAll('ms-prompt-chunk')] : [];
    const lastText = chunks.length ? (chunks[chunks.length - 1].textContent || '') : '';
    const stopBtns = [...document.querySelectorAll('button')].filter(b => /stop/i.test(b.textContent || '')).length;
    const lastTurnText = lastTurn ? (lastTurn.textContent || '') : '';
    return {
      turnCount: turns.length, stop: stopBtns > 0, lastTextLen: lastText.length,
      lastTurnHasV54: /Option \d+:/i.test(lastText) && /VisualBridge/i.test(lastText),
      lastTurnHasError: /internal error|failed to generate|permission denied|invalid argument/i.test(lastTurnText),
      lastTurnErrKind: (lastTurnText.match(/internal error|failed to generate|permission denied|invalid argument/i) || [''])[0]
    };
  });
}

// SI 状态探针 (只读, 不写入)
async function probeSI(page) {
  return await page.evaluate(() => {
    const tas = [...document.querySelectorAll('textarea[placeholder*="tone and style" i]')];
    const v = tas[0]?.value || '';
    return {
      hasTextarea: tas.length > 0,
      len: v.length,
      head: v.slice(0, 80).replace(/\s+/g, ' '),
      hasV54: /Amazon_VisualBridge/.test(v),
      isEmpty: v.trim().length === 0
    };
  });
}

async function fetchV54Answer(page) {
  return await page.evaluate(() => {
    const turns = [...document.querySelectorAll('ms-chat-turn')];
    const lastTurn = turns[turns.length - 1];
    if (!lastTurn) return null;
    const chunks = [...lastTurn.querySelectorAll('ms-prompt-chunk')];
    const answerIdx = chunks.findIndex(c => /Option \d+:/i.test(c.textContent || '') && /VisualBridge/i.test(c.textContent || ''));
    const i = answerIdx >= 0 ? answerIdx : chunks.length - 1;
    return { idx: i, text: chunks[i]?.textContent || '', len: chunks[i]?.textContent?.length || 0 };
  });
}

(async () => {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const page = (await browser.contexts()[0].pages()).find(p => /aistudio/.test(p.url()));
  console.log('URL', page.url());

  // 0. 真实最大化浏览器窗口 (CDP Browser domain, 不是 setViewportSize)
  try {
    const cdp = await page.context().newCDPSession(page);
    const { windowId } = await cdp.send('Browser.getWindowForTarget');
    await cdp.send('Browser.setWindowBounds', {
      windowId,
      bounds: { windowState: 'maximized' }
    });
    console.log('WINDOW_MAXIMIZED');
  } catch (e) {
    console.log('WINDOW_MAXIMIZE_FAIL', e.message, '(继续)');
  }
  await sleep(1500);

  // 1. 跳 new_chat
  if (!/prompts\/new_chat/.test(page.url())) {
    await page.locator('text="Playground"').first().click();
    await sleep(2500);
    console.log('NEW_CHAT_OK');
  } else {
    console.log('NEW_CHAT_SKIP');
  }
  await sleep(1500);

  // 2. SI 探针 (只读, 一次, 不等待)
  let siInfo = await probeSI(page);
  console.log('SI', JSON.stringify(siInfo));
  if (!siInfo.hasTextarea) {
    const opened = await page.evaluate(() => {
      const siBtn = [...document.querySelectorAll('button, [role="button"]')].find(e =>
        e.getAttribute('aria-label') === 'System instructions' ||
        (e.textContent || '').trim() === 'System instructions');
      if (siBtn) { siBtn.click(); return true; }
      return false;
    });
    console.log('SI_EXPAND_CLICK', opened);
    await sleep(1500);
    siInfo = await probeSI(page);
    console.log('SI_AFTER_EXPAND', JSON.stringify(siInfo));
  }
  if (!siInfo.hasV54) {
    console.log('SI_NOT_V54 — 写 si_required.json 通知用户, 脚本不等待');
    fs.writeFileSync(path.join(SKILL_OUT, 'si_required.json'), JSON.stringify({
      ts: new Date().toISOString(),
      msg: '>>> USER_NOTIFY: 请手动切/粘 POD-印花底稿-v5.4 到 System instructions, 然后自己关掉 SI 编辑面板 <<<',
      recordId
    }, null, 2));
  } else {
    console.log('SI_OK (已有 v5.4)');
  }

  // ★ 步骤 2.5 删除: SI 关面板由用户自己负责, 脚本不做 Esc/blur

  // 3. 写入主输入框
  const inputRes = await page.evaluate(async (url) => {
    const r = await fetch(url);
    const bytes = new Uint8Array(await r.arrayBuffer());
    const text = new TextDecoder('utf-8').decode(bytes);
    const tas = [...document.querySelectorAll('textarea[placeholder*="Start typing a prompt"]')];
    if (!tas.length) return JSON.stringify({ err: 'no input textarea' });
    const ta = tas[0];
    const desc = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
    desc.set.call(ta, text);
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    return JSON.stringify({ ok: true, len: ta.value.length });
  }, `http://127.0.0.1:${httpPort}/input`);
  console.log('INPUT', inputRes);
  await sleep(2000);

  // 4. Ctrl+Enter Run
  await page.keyboard.press('Control+Enter');
  console.log('RUN_TRIGGERED');
  await sleep(3000);

  // 5. 探针是否触发
  const initialState = await probeState(page);
  if (initialState.turnCount <= 1) {
    // ★ 兜底删除: 不再自动 click Run, 停止等待
    console.log('CTRL_ENTER_NOOP (turnCount<=1) — 停止等待, 写 si_required.json 通知用户');
    fs.writeFileSync(path.join(SKILL_OUT, 'si_required.json'), JSON.stringify({
      ts: new Date().toISOString(),
      msg: '>>> USER_NOTIFY: Ctrl+Enter 没触发 Run (可能 SI 面板没关, 或输入框没聚焦), 请手动在浏览器里点 Run 按钮 <<<',
      state: initialState,
      recordId
    }, null, 2));
    // 不退出, 让监控循环继续 (用户手动 Run 后会进入生成流程)
  } else {
    console.log(`TURN_CREATED (turnCount=${initialState.turnCount})`);
  }

  // 6. 监控循环
  const startTime = Date.now();
  let notifiedAt = 0;
  let userRerunCount = 0;
  while (Date.now() - startTime < 600000) {
    await sleep(5000);
    const state = await probeState(page);
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    console.log(`  [${elapsed}s] turn=${state.turnCount} stop=${state.stop} textLen=${state.lastTextLen} err=${state.lastTurnErrKind || '-'} v54=${state.lastTurnHasV54} reruns=${userRerunCount}`);

    if (state.lastTurnHasV54) {
      const ans = await fetchV54Answer(page);
      const stamp = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19);
      const report = `# AI Studio 半自动协作 - ${stamp} - ${recordId}\n\n## 输入\n\`\`\`\n${PRODUCT}\n\`\`\`\n\n## v5.4 答案（${ans.len} 字符, chunk #${ans.idx}）\n\`\`\`\n${ans.text}\n\`\`\`\n\n## 协作模式\n- 脚本自动: 最大化窗口 / SI探针(不写入) / 输入 / Run / 监控 / 抓取\n- 用户手动: SI切换并关面板 / ${userRerunCount} 次 "Rerun this turn"\n`;
      const outFile = path.join(SKILL_OUT, `half_auto_${recordId}_${stamp}.md`);
      fs.writeFileSync(outFile, report, 'utf8');
      console.log('SAVED', outFile);
      server.close();
      await browser.close();
      process.exit(0);
    }

    const realError = state.turnCount >= 2 && !state.stop && state.lastTurnHasError;
    if (realError && notifiedAt === 0) {
      notifiedAt = Date.now();
      userRerunCount = 1;
      const notice = {
        ts: new Date().toISOString(),
        msg: '>>> USER_NOTIFY: 服务端拒绝, 请手动点 "Rerun this turn" <<<',
        state,
        elapsedSec: elapsed,
        recordId
      };
      fs.writeFileSync(path.join(SKILL_OUT, 'last_error.json'), JSON.stringify(notice, null, 2));
      console.log(`>>> USER_NOTIFY: 请手动点 "Rerun this turn" <<<  (err=${state.lastTurnErrKind})`);
    }

    if (notifiedAt > 0 && state.turnCount > userRerunCount) {
      console.log('  USER_RERUN_DETECTED — 错误已清, 脚本继续监控');
      notifiedAt = 0;
      userRerunCount = state.turnCount;
    }
  }

  console.log('TIMEOUT (10分钟)');
  server.close();
  await browser.close();
  process.exit(1);
})().catch(e => { console.error('FATAL', e.message); process.exit(1); });
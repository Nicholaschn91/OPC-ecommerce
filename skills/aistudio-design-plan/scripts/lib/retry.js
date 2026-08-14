'use strict';
/**
 * lib/retry.js  —  错误检测 + Rerun（精确点 user turn）+ 退避策略
 *
 * 关键修复：rerunTurn 必须用「真实鼠标坐标点击」(page.mouse.click，CDP Input 受信通道，
 * isTrusted=true) 触发重跑。原先在 page.evaluate 内调用 element.click() 是合成事件
 * (isTrusted=false)，AI Studio 反爬据此判定为自动化 → 持续返回 internal error。
 * 这也解释了「手动点 Rerun 能过、脚本点 4 次都不过」的现象。
 */
const { sleep } = require('./constants');
const { osClickAt, osClickEnabled } = require('./osclick');

const ERROR_PATTERNS = [
  /internal error/i,
  /permission denied/i,
  /failed to generate/i,
];

const QUOTA_PATTERNS = [
  /rate limit/i,
  /too many requests/i,
  /quota/i,
  /you'?ve (reached|hit) (the|a)? ?limit/i,
  /you have (reached|hit) (the|a)? ?limit/i,
  /daily limit/i,
  /free tier limit/i,
  /exceeded.*(request|rate|quota)/i,
  /please try again later/i,
  /try again in \d+/i,
];

function detectQuota(text) {
  return QUOTA_PATTERNS.some((re) => re.test(text));
}

async function hasError(page) {
  const text = await page
    .evaluate(() => {
      const turns = [...document.querySelectorAll('ms-chat-turn')];
      if (!turns.length) return '';
      for (let i = turns.length - 1; i >= 0; i--) {
        const t = (turns[i].innerText || '').trim();
        if (t) return t;
      }
      return '';
    })
    .catch(() => '');
  return ERROR_PATTERNS.some((re) => re.test(text));
}

/**
 * rerunTurn — 只点 user turn（报错块前一条）的 Rerun this turn，绝不回退到模型块
 * 返回 true 表示已用真实鼠标点击触发重跑
 */
async function rerunTurn(page, errIdx, log) {
  const info = await page.evaluate((errIdx) => {
    const turns = [...document.querySelectorAll('ms-chat-turn')];
    const errTurn = turns[errIdx];
    if (!errTurn) return { ok: false, why: 'NO_ERR_TURN' };
    const userTurn = turns[errIdx - 1];
    if (!userTurn) return { ok: false, why: 'NO_USER_TURN' };
    const btns = [...userTurn.querySelectorAll('button')];
    const r = btns.find((b) => {
      const a = (b.getAttribute('aria-label') || '').trim();
      const t = (b.textContent || '').trim();
      return a === 'Rerun this turn' || /rerun this turn/i.test(a) || /rerun this turn/i.test(t);
    });
    if (!r) {
      return {
        ok: false,
        why: 'NO_RERUN_IN_USER_TURN',
        userButtons: btns
          .map((b) => (b.getAttribute('aria-label') || '') + '|' + (b.textContent || '').trim())
          .slice(0, 10),
      };
    }
    r.scrollIntoView({ block: 'center' });
    const rect = r.getBoundingClientRect();
    return {
      ok: true,
      cx: rect.left + rect.width / 2,
      cy: rect.top + rect.height / 2,
      label: r.getAttribute('aria-label') || r.textContent.trim(),
    };
  }, errIdx);

  if (info.ok) {
    // 关键修复：真实鼠标坐标点击（受信手势），非 evaluate 内 element.click()（合成事件）
    await sleep(150);
    if (osClickEnabled()) await osClickAt(page, info.cx, info.cy, log);
    else await page.mouse.click(info.cx, info.cy);
    if (log) log('  [Rerun] 已用真实鼠标点击 user 内容框的「Rerun this turn」(label="' + info.label + '")');
    return true;
  }
  if (log) log('  [Rerun] 未在 user 内容框找到「Rerun this turn」: ' + JSON.stringify(info));
  return false;
}

/**
 * waitResponse — 生成等待 + Rerun（递增退避 + 限流识别）
 */
async function waitResponse(page, timeoutMs, log) {
  const deadline = Date.now() + timeoutMs;
  let last = '';
  let stable = 0;
  let saved = false;
  let retries = 4; // 最大 Rerun 次数
  let backoff = 15000; // 首次 15s，每次 +15s，上限 120s

  while (Date.now() < deadline) {
    await sleep(3000);

    if (!saved && !/new_chat/.test(page.url())) {
      saved = true;
      log('  会话已存盘: ' + page.url());
    }

    const state = await page
      .evaluate(() => {
        const turns = [...document.querySelectorAll('ms-chat-turn')];
        return turns.map((t) => (t.innerText || '').trim());
      })
      .catch(() => []);

    let cur = '';
    let curIdx = -1;
    for (let i = state.length - 1; i >= 0; i--) {
      if (state[i]) { cur = state[i]; curIdx = i; break; }
    }

    if (cur && ERROR_PATTERNS.some((re) => re.test(cur))) {
      const isQuota = detectQuota(cur);
      if (retries > 0) {
        retries--;
        const waitMs = isQuota ? Math.max(backoff, 45000) : backoff;
        log('  检测到报错 (turn ' + curIdx + (isQuota ? ', 疑似限流/免费额度耗尽' : '') +
          ')，Rerun (' + retries + ' 剩余)，退避 ' + Math.round(waitMs / 1000) + 's');
        if (process.env.AI_STUDIO_DEBUG) {
          const rep = await page.evaluate((errIdx) => {
            const turns = [...document.querySelectorAll('ms-chat-turn')];
            const dump = (t, i) => {
              const btns = [...t.querySelectorAll('button')].map(b => ({
                label: (b.getAttribute('aria-label') || '').trim(),
                text: (b.textContent || '').trim(),
                isRerunThisTurn: (b.getAttribute('aria-label') || '').trim() === 'Rerun this turn' || /rerun this turn/i.test(b.textContent||''),
              })).filter(b => /rerun|retry|重新运行/i.test(b.label + b.text));
              return {
                idx: i,
                isUser: !!t.querySelector('textarea'),
                isErrTurn: i === errIdx,
                rerunBtns: btns,
                head: (t.innerText || '').slice(0, 40).replace(/\n/g, ' '),
              };
            };
            return [dump(turns[errIdx - 1], errIdx - 1), dump(turns[errIdx], errIdx)].filter(Boolean);
          }, curIdx).catch(e => 'eval_err:' + e);
          log('  [DEBUG] errTurn=' + curIdx + ' userTurnRerun=' + JSON.stringify(rep));
          await page.screenshot({ path: 'dp_run/debug_err_' + (4 - retries) + '.png' }).catch(() => {});
        }
        await rerunTurn(page, curIdx, log);
        last = '';
        stable = 0;
        await sleep(waitMs);
        backoff = Math.min(backoff + 15000, 120000);
        continue;
      }
      const quotaTag = isQuota ? '【限流/免费额度耗尽】' : '';
      throw new Error((quotaTag + '模型持续报错') +
        '（已 Rerun ' + (4 - retries) + ' 次）：' + cur.slice(0, 200));
    }

    if (cur && cur === last) {
      stable++;
      if (stable >= 5) return cur; // 连续 15s 无变化 → 判定结束
    } else {
      if (cur && cur.length !== last.length) {
        log('  生成中... ' + cur.length + ' 字符');
      }
      stable = 0;
      last = cur;
    }
  }
  if (last) {
    log('  达到超时，返回当前已抓取内容');
    return last;
  }
  throw new Error('生成超时：未抓取到模型回复');
}

module.exports = { hasError, rerunTurn, waitResponse };

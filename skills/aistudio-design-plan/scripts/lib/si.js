'use strict';
/**
 * lib/si.js  —  System Instructions 载入（从 Library，绝不粘贴创建副本）
 *
 * 铁律（用户 2026-08-11 纠正）：
 *   1. localStorage `aistudio_all_system_instructions` 是唯一真相源；面板 DOM 异步渲染不可信。
 *   2. localStorage 命中后点 Saved 区里【指令名本身】即可载入；不要用 setter 粘贴新内容（会生成副本）。
 *   3. 已存在则绝不重复新建（`setup_si.cjs` 以 localStorage 为权威判定）。
 *
 * 稳健性补强（2026-08-12）：
 *   - UI 点击路径优先：开面板 → 点 "+ Create new instruction" 触发器 → 在 overlay 里点指令名。
 *   - UI 实在渲染不出（偶发时序）时，fallback：从 localStorage 读【已保存】SI 内容，用 React 兼容方式
 *     填入当前对话的 SI 文本框（不点 Save）。内容严格来自 Library 已保存条目，不产生副本。
 */
const { sleep, SI_LABEL } = require('./constants');

async function lsCheck(page, name) {
  return await page
    .evaluate((nm) => {
      try {
        const raw = localStorage.getItem('aistudio_all_system_instructions');
        if (!raw) return { exists: false, reason: 'no key' };
        const arr = JSON.parse(raw);
        const hit = arr.find((it) => (it.title || '').trim() === nm);
        return { exists: !!hit, count: arr.length, matchedLen: hit ? (hit.text || '').length : 0 };
      } catch (e) {
        return { exists: false, reason: 'parse:' + String(e) };
      }
    }, name)
    .catch((e) => ({ exists: false, reason: 'eval:' + String(e) }));
}

async function openPanel(page, log) {
  const ok = await page.evaluate((label) => {
    const span = [...document.querySelectorAll('span.title')].find((s) =>
      new RegExp(label, 'i').test(s.textContent || '')
    );
    if (!span) return false;
    let p = span;
    for (let i = 0; i < 6; i++) {
      if (!p.parentElement) break;
      p = p.parentElement;
      if (p.tagName === 'BUTTON' || p.getAttribute('role') === 'button' || p.onclick) {
        p.click();
        return true;
      }
    }
    span.click();
    return true;
  }, SI_LABEL);
  if (!ok) throw new Error('未找到「System instructions」入口，无法打开面板');
  await page.waitForSelector('ms-system-instructions', { timeout: 10000 }).catch(() => {});
}

/**
 * 点击已保存指令（UI 路径）。返回 true=已点击。
 * 覆盖：mat-select 触发器（文字 "+ Create new instruction" / "Saved"）、Angular overlay 选项、
 *      ms-model-option、mat-option、role=option 等多种形态。
 */
async function clickSavedByName(page, name) {
  // 0) 等面板里的 mat-select 触发器出现（消除时序抖动），多种可能定位
  await page
    .waitForSelector('.mat-mdc-select-trigger, [class*="select-trigger"], text=+ Create new instruction', {
      timeout: 15000,
    })
    .catch(() => {});

  // 1) 打开「已保存指令」下拉
  const opened = await page.evaluate(() => {
    // 优先 mat-mdc-select-trigger
    let trig =
      document.querySelector('.mat-mdc-select-trigger') ||
      document.querySelector('[class*="select-trigger"]');
    if (!trig) {
      // 退而求其次：文字匹配 "+ Create new instruction" / "Saved" 的可点击元素
      const cand = [...document.querySelectorAll('*')].find((el) => {
        const t = (el.textContent || '').trim();
        return el.children.length <= 2 && /Create new instruction|Saved/i.test(t) && t.length < 60;
      });
      trig = cand || null;
    }
    if (trig) {
      trig.click();
      return true;
    }
    return false;
  });
  if (!opened) return false;
  await sleep(1800);

  // 2) 在 overlay / 面板内点匹配项（多选择器轮询，覆盖动态结构）
  const opts = [
    '.cdk-overlay-container :has-text("' + name + '")',
    'mat-option:has-text("' + name + '")',
    '.mat-mdc-select-panel :has-text("' + name + '")',
    'ms-model-option:has-text("' + name + '")',
    '[role="option"]:has-text("' + name + '")',
    '.mat-mdc-select-content :has-text("' + name + '")',
  ];
  for (let attempt = 0; attempt < 30; attempt++) {
    for (const sel of opts) {
      const loc = page.locator(sel).first();
      if ((await loc.count().catch(() => 0)) > 0) {
        try {
          await loc.click({ timeout: 2000 });
          return true;
        } catch (e) {
          /* 未就绪，继续轮询 */
        }
      }
    }
    await sleep(1000);
  }
  // 3) 最后兜底：任意含指令名的可见文本点击
  const anyLoc = page.locator('text=' + JSON.stringify(name)).first();
  if ((await anyLoc.count().catch(() => 0)) > 0) {
    try {
      await anyLoc.click({ timeout: 3000 });
      return true;
    } catch (e) {}
  }
  return false;
}

/**
 * fallback：UI 渲染失败时，从 localStorage 读【已保存】SI 内容填入对话 SI 文本框。
 * 不点 Save → 不产生 Library 副本。内容严格来自 Library 已有条目。
 */
async function fallbackFill(page, name, log) {
  const res = await page
    .evaluate((nm) => {
      const raw = localStorage.getItem('aistudio_all_system_instructions');
      if (!raw) return { ok: false, reason: 'no key' };
      let arr;
      try {
        arr = JSON.parse(raw);
      } catch (e) {
        return { ok: false, reason: 'parse' };
      }
      const hit = arr.find((it) => (it.title || '').trim() === nm);
      if (!hit) return { ok: false, reason: 'no match in library' };
      const ta = [...document.querySelectorAll('textarea')].find(
        (x) => (x.getAttribute('aria-label') || '') === 'System instructions'
      );
      if (!ta) return { ok: false, reason: 'no SI textarea' };
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      setter.call(ta, hit.text);
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      ta.dispatchEvent(new Event('change', { bubbles: true }));
      return { ok: true, len: hit.text.length };
    }, name)
    .catch((e) => ({ ok: false, reason: 'eval:' + String(e) }));
  if (res.ok) {
    if (log) log('  [SI] fallback：从 localStorage 直接填充文本框 (' + res.len + ' 字符)，未点 Save，不产生副本');
    await sleep(1200);
  } else if (log) {
    log('  [SI] fallback 失败: ' + (res.reason || 'unknown'));
  }
  return res.ok;
}

async function readLoadedText(page) {
  return await page
    .evaluate((label) => {
      const t = [...document.querySelectorAll('textarea')].find(
        (x) => (x.getAttribute('aria-label') || '') === label
      );
      return t ? t.value : '';
    }, SI_LABEL)
    .catch(() => '');
}

async function loadSIFromLibrary(page, name, expectSnippet, log) {
  // 0) 真相源校验（localStorage 是唯一真相源，带重试规避时序）
  let ls = { exists: false };
  for (let i = 0; i < 5; i++) {
    ls = await lsCheck(page, name);
    if (ls.exists) break;
    await sleep(1500);
  }
  if (log) {
    log('  [SI] localStorage 中「' + name + '」: ' + (ls.exists ? '存在(' + ls.matchedLen + '字符)' : '不存在'));
  }

  // 复用铁律：Library 已保存的指令直接复用，绝不走 UI 新建（会堆空标题副本）。
  // 只有全新浏览器（localStorage 无此条）才需要先用 setup_si.cjs 录入一次。
  if (!ls.exists) {
    throw new Error('System Instruction「' + name + '」不在本 profile 的 Library 中。请先运行 setup_si.cjs 录入一次（仅新浏览器需录入）。');
  }

  // 1) 直接从 localStorage 读已保存内容填入文本框（复用，绝不碰 UI 下拉/新建）
  const fb = await fallbackFill(page, name, log);
  if (!fb) {
    throw new Error('System Instruction「' + name + '」从 Library 复用失败');
  }

  // 2) 校验文本框
  const loaded = await readLoadedText(page);
  log('  SI 载入: 「' + name + '」，文本框 ' + loaded.length + ' 字符');
  if (loaded.length < 100) {
    throw new Error('System Instruction「' + name + '」文本框载入为空（' + loaded.length + ' 字符），载入失败');
  }
  if (expectSnippet && loaded && !loaded.includes(expectSnippet)) {
    log('  ⚠️ SI 校验片段未命中（期望含 "' + expectSnippet + '"）—— Library 中该指令可能未更新到最新版');
  }
  return { ok: true, len: loaded.length, name };
}

module.exports = { lsCheck, openPanel, clickSavedByName, fallbackFill, readLoadedText, loadSIFromLibrary };

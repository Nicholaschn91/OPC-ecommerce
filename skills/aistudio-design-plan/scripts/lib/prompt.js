'use strict';
/**
 * lib/prompt.js  —  注入商品信息 Prompt（�触发 Angular 表单更新）
 */
const { sleep, SEL_PROMPT } = require('./constants');

async function inject(page, text, log) {
  await page.waitForSelector(SEL_PROMPT, { timeout: 30000 });
  // 关闭可能�挡住输入�框的�遮�罩�层
  const { closeOverlays } = require('./browser');
  await closeOverlays(page, log);

  const ed = page.locator(SEL_PROMPT).first();
  try {
    await ed.click({ timeout: 10000 });
    // 人类化逐字输入（带抖动延时）代替瞬时 .fill() 粘贴，降低被识别为自动化的概率
    const delay = Math.max(8, Math.min(45, Math.round(4000 / Math.max(1, text.length))));
    await page.keyboard.type(text, { delay });
  } catch (e) {
    // �兜底：�绕过点击，直接走 native setter �触发 Angular 表单更新
    if (log) log('  点击受�阻，改用 native setter �兜底注入');
    await page.evaluate(
      ({ sel, value }) => {
        const t = document.querySelector(sel);
        if (!t) throw new Error('prompt textarea not found');
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype,
          'value'
        ).set;
        setter.call(t, value);
        t.dispatchEvent(new Event('input', { bubbles: true }));
        t.dispatchEvent(new Event('change', { bubbles: true }));
        t.focus();
      },
      { sel: SEL_PROMPT, value: text }
    );
  }
  await sleep(800);
  const v = await ed.inputValue().catch(() => '');
  return v.length;
}

module.exports = { inject };

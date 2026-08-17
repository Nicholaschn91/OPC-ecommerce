// 确定性切模型脚本：把当前千问对话固定到 Qwen3.8-Max（或更高）。
// 仅做"读徽标→非3.8-Max则点开选择器→点 Qwen3.8-Max 行→再读徽标断言"这一步。
// 其余步骤仍由人工/逐次 skill 调用完成（不在此批量自动化）。
async (page) => {
  const sleep = (ms) => page.waitForTimeout(ms);
  const TARGET = 'Qwen3.8-Max';

  // 先关掉任何残留下拉，回到确定性"关闭态"（避免上一次交互遗留的打开态被本次点击误关）
  await page.keyboard.press('Escape');
  await sleep(300);

  // 读当前模型徽标（叶子节点，文本含 Qwen3 且带 text-16 样式）
  const readBadge = () => page.evaluate(() => {
    const els = [...document.querySelectorAll('*')].filter(e =>
      e.children.length === 0 &&
      /Qwen3/.test(e.textContent || '') &&
      /text-16/.test((e.className || '').toString()));
    return els.length ? els[0].textContent.trim() : null;
  });

  const before = await readBadge();
  if (before && before.includes(TARGET)) {
    return { ok: true, already: true, badge: before };
  }

  // 点徽标开选择器
  const opened = await page.evaluate(() => {
    const els = [...document.querySelectorAll('*')].filter(e =>
      e.children.length === 0 &&
      /Qwen3/.test(e.textContent || '') &&
      /text-16/.test((e.className || '').toString()));
    if (!els.length) return false;
    els[0].click();
    return true;
  });
  if (!opened) return { ok: false, reason: 'badge-not-found', before };

  // 点 Qwen3.8-Max 选项行（cursor-pointer 的模型行，排除顶部快捷栏胶囊）
  let picked = false;
  for (let i = 0; i < 4 && !picked; i++) {
    await sleep(1000);
    picked = await page.evaluate((target) => {
      const rows = [...document.querySelectorAll('div')].filter(e =>
        /cursor-pointer/.test((e.className || '').toString()) &&
        e.textContent.includes(target));
      if (!rows.length) return false;
      rows[0].click();
      return true;
    }, TARGET);
  }
  if (!picked) return { ok: false, reason: 'option-not-found', before };

  await sleep(800);

  // 二次读徽标断言
  const after = await readBadge();
  const ok = !!(after && after.includes(TARGET));
  return { ok, before, after, reason: ok ? null : 'badge-not-3.8max-after-click' };
}

// 嗅探脚本：注入到 qianwen 页面，捕获所有图片 URL（含接口返回的 JSON 中的原图地址）
(function () {
  window.__qw = [];
  window.__qwSeen = new Set();

  function classify(url) {
    const u = url.toLowerCase();
    const wm = /watermark|\?.*wm=|[\?&]wm|thumb|_thumb|\/thumb|x-oss-process|compress|\?x-oss/i.test(u);
    const isImg = /\.(jpg|jpeg|png|webp|gif|avif|bmp)(\?|$)/i.test(u) || /image\//.test(u);
    return { wm, isImg };
  }

  function add(url, where) {
    if (!url || url.startsWith('data:') || url.startsWith('blob:')) return;
    if (window.__qwSeen.has(url)) return;
    window.__qwSeen.add(url);
    const c = classify(url);
    window.__qw.push({ url, where, watermark: c.wm, img: c.isImg, t: Date.now() });
    console.log('[qw] ' + where + (c.wm ? ' (WM)' : ' (CLEAN?)') + ' ' + url.slice(0, 140));
  }

  // 从任意文本里抽图片 URL
  function scanText(txt, where) {
    if (!txt) return;
    const re = /https?:\/\/[^\s"'`)}\\]+?\.(?:jpg|jpeg|png|webp|gif|avif|bmp)(?:\?[^"'`)}\\]*)?/gi;
    let m;
    while ((m = re.exec(txt))) add(m[0], where);
  }

  // fetch 劫持
  const _fetch = window.fetch.bind(window);
  window.fetch = function (...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    return _fetch.apply(window, args).then(async (resp) => {
      try {
        const ct = resp.headers.get('content-type') || '';
        if (ct.startsWith('image/')) add(resp.url, 'fetch-image');
        else if (ct.includes('json')) {
          const clone = resp.clone();
          const txt = await clone.text();
          scanText(txt, 'fetch-json');
        }
      } catch (e) {}
      return resp;
    });
  };

  // XHR 劫持
  const _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__qwUrl = url;
    return _open.apply(this, arguments);
  };
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener('load', function () {
      try {
        const ct = this.getResponseHeader('content-type') || '';
        if (ct.includes('json')) scanText(this.responseText, 'xhr-json');
      } catch (e) {}
    });
    return _send.apply(this, arguments);
  };

  // DOM 图片扫描（含懒加载 data-src）
  setInterval(() => {
    document.querySelectorAll('img').forEach((img) => {
      add(img.getAttribute('src'), 'img-src');
      add(img.getAttribute('data-src') || img.getAttribute('data-original'), 'img-data-src');
      add(img.getAttribute('srcset'), 'img-srcset');
    });
  }, 1500);

  console.log('[qw] 嗅探已挂载 ✅ 所有图片 URL 将记录到 window.__qw');
})();

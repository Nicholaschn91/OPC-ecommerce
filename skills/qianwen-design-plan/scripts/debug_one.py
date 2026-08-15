#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debug_one.py — 单条诊断：注入+发送后打印页面正文，定位拒答原因。"""
import os, re, sys, time
for _k in ["HTTPS_PROXY","HTTP_PROXY","https_proxy","http_proxy","ALL_PROXY","all_proxy"]:
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

import run_dp_batch as R
from playwright.sync_api import sync_playwright

rid = sys.argv[1] if len(sys.argv) > 1 else "recvoVGmlb31hD"
variant = int(sys.argv[2]) if len(sys.argv) > 2 else 0

si = R.read_si()
data = R.get_product(rid)
full = R.build_full(variant, si, data, R.DEFAULT_LAUNCH)
print(f"=== prompt({len(full)} chars) head ===\n{full[:400]}\n...tail...\n{full[-300:]}\n", flush=True)

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp(R.CDP_URL)
    ctx = b.contexts[0] if b.contexts else b.new_context()
    page = ctx.new_page()
    page.set_default_timeout(60000)

    fc = R.force_new_conversation(page)
    print("force_new:", fc, flush=True)
    m = R.ensure_model(page)
    print("model:", m, flush=True)

    inlen = R.inject_prompt(page, full)
    print("injected len:", inlen, "expected:", len(full), flush=True)
    sent = R.click_send(page)
    print("sent:", sent, flush=True)

    # poll, capture body on refused
    state = "generating"
    body = ""
    start = time.time()
    while time.time() - start < 240:
        info = page.evaluate(r"""() => {
          const t = document.body.innerText || '';
          const rounds = document.querySelectorAll('.chat-round');
          const stopBtn = Array.from(document.querySelectorAll('button')).find(btn => {
            const a = btn.getAttribute('aria-label') || '';
            const x = btn.textContent || '';
            return a.includes('停止') || x.includes('停止生成');
          });
          const refused = t.includes('无法回答') || t.includes('我们聊聊别的');
          let ll = 0;
          if (rounds.length > 0) ll = (rounds[rounds.length-1].innerText || '').length;
          return { stopBtn: !!stopBtn, refused, lastLen: ll, bodyLen: t.length };
        }""")
        if info["refused"]:
            state = "refused"
            body = page.evaluate("() => document.body.innerText")
            break
        if (not info["stopBtn"]) and info["lastLen"] > 300:
            time.sleep(2.5)
            len2 = page.evaluate(r"""() => {
              const r = document.querySelectorAll('.chat-round');
              return r.length ? (r[r.length-1].innerText||'').length : 0;
            }""")
            if len2 == info["lastLen"]:
                state = "done"
                body = page.evaluate("() => { const r=document.querySelectorAll('.chat-round'); return r.length?r[r.length-1].innerText:''; }")
                break
        time.sleep(2.5)

    print(f"\n=== STATE: {state} ===", flush=True)
    print("BODY (last 2500 chars):", flush=True)
    print(body[-2500:], flush=True)

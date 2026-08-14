#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qwen_gen.py — 千问 AI生图 确定性 CLI（弱智模型友好 / 已把全部已知坑烘焙进代码）

设计目标：让一个弱智模型只要会"跑一条命令"就能完成 千问图生图 + 无水印原图下载，
而不是去读 SKILL.md 的散文、自己推理怎么绕 pointer-events / 比例控件 / CDN 域名 /
指纹被标黑。所有坑都在本文件里用确定代码处理掉了。

A 路线（反检测）：直接用 CloakBrowser 隐身 Chromium 启动（指纹层 webdriver=false，
避免标准 Chrome + cdp-profile-h 被千问风控标黑导致 WebSocket 403 生不出图）。

已烘焙的坑（与 SKILL.md 关键陷阱一一对应）：
  #4/#7  比例由 UI 控件决定（不靠 prompt 文本）；真实图落到 workspace-zb-cdn（host-agnostic 抓取）
  #10    导航 qianwen.com/chat（绝不写 www，DNS 会失败）
  #11    菜单项被父容器拦截 pointer events → 用 JS click 绕
  #12    被识别/风控 → CloakBrowser 隐身二进制启动（A 路线）
  +      生成中先出 gradient 占位 → 至少 30s 冷却再抓最终图
  +      未登录 → 明确报错并给出 --login 指引，不瞎跑

用法：
  # 图生图 + 下载（默认无头；依赖已登录的 cloak-cdp-profile）
  python qwen_gen.py --prompt "一只咖啡色疯马皮短夹，正面居中" --ref ref.png --ratio 1:1 --out ./gen

  # 仅登录（有头窗口，手登 / 过滑块后关闭，profile 自动持久化）
  python qwen_gen.py --login

  # 只读探测：打开千问，报告是否已登录，不生成（用于先验 A 路线是否还会被识别）
  python qwen_gen.py --check

  # 整页收割：不重新生成，把当前页已渲染的无水印原图全下载
  python qwen_gen.py --harvest --out ./harvest

依赖：CloakBrowser 已装（cloakbrowser doctor 显示 Binary 路径）；本 venv 含 playwright。
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import urllib.request

# ---- 路径（与 cloakbrowser doctor 输出一致；CloakBrowser 升级版本号会变，这里用 env 覆盖）----
CLOAK = os.environ.get(
    "QWEN_CLOAK_BIN",
    r"C:\Users\nicho\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe",
)
PROFILE = os.environ.get(
    "QWEN_PROFILE",
    r"C:\Users\nicho\.workbuddy\chrome-profiles\cloak-cdp-profile",
)
QW_URL = os.environ.get("QWEN_URL", "https://qianwen.com/chat")  # 注意：无 www

# 下载原图时排除的水印/缩略图特征
WM_RE = re.compile(r"watermark|wm|thumb|x-oss-process|compress|avatar|icon|emoji", re.I)
# 真实生成图 host（实测 workspace-zb-cdn.qianwen.com；host-agnostic 兜底见下）
CDN_RE = re.compile(r"workspace-zb-cdn", re.I)


def log(*a):
    print("[qwen_gen]", *a, flush=True)


def get_cloak_bin():
    """优先用环境变量，否则尝试从 cloakbrowser info 解析二进制路径。"""
    if os.path.exists(CLOAK):
        return CLOAK
    try:
        out = subprocess.run(
            [r"C:\Users\nicho\.workbuddy\binaries\python\envs\default\Scripts\cloakbrowser", "info"],
            capture_output=True, text=True, timeout=30,
        ).stdout
        m = re.search(r"Binary:\s*(\S+)", out)
        if m and os.path.exists(m.group(1)):
            return m.group(1)
    except Exception as e:
        log("解析 cloakbrowser info 失败:", e)
    return CLOAK


async def js_click_by_text(page, text, timeout=4000):
    """用 JS click 绕 pointer-events 拦截（坑 #11）。找不到返回 False。"""
    return await page.evaluate(
        """(t) => {
            const it=[...document.querySelectorAll('*')].filter(
                e=>(e.innerText||'').trim()===t && e.children.length===0 && e.offsetParent!==null);
            if(it.length){ it[0].click(); return true; }
            return false;
        }""",
        text,
    )


async def in_ai_image_mode(page):
    return await page.evaluate(
        """() => /参考图|创意生图|智能修图|比例/.test(document.body.innerText)
                  && !!([...document.querySelectorAll('[contenteditable]')].find(e=>e.offsetParent!==null))"""
    )


async def enter_ai_image_mode(page):
    if await in_ai_image_mode(page):
        log("已在 AI生图 模式")
        return True
    # 策略1：底栏 aria-label="AI生图"
    try:
        await page.get_by_label("AI生图").click(timeout=4000, force=True)
        await page.wait_for_timeout(1500)
        if await in_ai_image_mode(page):
            log("经底栏按钮进入 AI生图")
            return True
    except Exception:
        pass
    # 策略2：更多 → 下拉 AI生图（用 JS click 绕 pointer-events 坑 #11）
    if await js_click_by_text(page, "更多"):
        await page.wait_for_timeout(800)
        if await js_click_by_text(page, "AI生图"):
            await page.wait_for_timeout(1800)
            if await in_ai_image_mode(page):
                log("经『更多』下拉进入 AI生图")
                return True
    log("⚠️ 未能确认进入 AI生图 模式，仍尝试继续")
    return False


async def start_new_chat_in_same_tab(page, log):
    """
    用户 2026-08-13 22:5x 强制要求：复用同 tab 起新任务，绝不开新 tab。
    优先级：
      1) 点 sidebar 上 「新建对话」按钮
      2) page.goto(QW_URL) 同 tab 重导航
    """
    # 1) 优先：sidebar/header 上的「新建对话」按钮
    candidates = [
        # 千问新建对话按钮通常带 + 图标，文本"新建对话"
        ('role=button[name="新建对话"]', None),
        ('role=button[name="新对话"]', None),
        ('role=link[name="新建对话"]', None),
        ('text="新建对话"', None),
        ('text="新对话"', None),
    ]
    for sel, _ in candidates:
        try:
            if sel.startswith('role='):
                role_name = sel[len('role='):].split('[')[-1].rstrip(']').strip('"').strip("'")
                # 简单手搓
                if 'button' in sel:
                    el = page.get_by_role("button", name=role_name).first
                elif 'link' in sel:
                    el = page.get_by_role("link", name=role_name).first
                else:
                    continue
            elif sel.startswith('text='):
                txt = sel[len('text='):].strip('"').strip("'")
                el = page.get_by_text(txt).first
            else:
                continue
            if await el.count() > 0 and await el.is_visible():
                await el.click(timeout=3000)
                await page.wait_for_timeout(1500)
                log(f"  ✓ in-page 新建对话: {sel}")
                return True
        except Exception:
            continue
    # 2) 兜底：同 tab navigate QW_URL（不开新 tab）
    log("  → fallback: 同 tab 重导 " + QW_URL)
    await page.goto(QW_URL, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2500)
    return True


async def set_ratio(page, ratio):
    try:
        await page.get_by_role("button", name=re.compile("比例")).click(timeout=4000)
        await page.wait_for_timeout(500)
        await page.get_by_text(ratio, exact=True).first.click(timeout=4000)
        await page.wait_for_timeout(400)
        cur = await page.evaluate(
            "() => { const b=[...document.querySelectorAll('button')].find(x=>(x.textContent||'').includes('比例')); return b?b.textContent.trim():''; }"
        )
        log("比例控件:", cur)
    except Exception as e:
        log("⚠️ 设置比例失败（将沿用默认）:", e)


async def collect_clean_imgs(page):
    """host-agnostic 抓无水印原图：naturalWidth 够大且无水印特征，或命中 CDN host。"""
    return await page.evaluate(
        """() => {
            const r=[];
            document.querySelectorAll('img').forEach(i=>{
                const s=i.src||'';
                if(!s) return;
                const clean = !/watermark|wm|thumb|x-oss-process|compress|avatar|icon|emoji/i.test(s);
                const big = (i.naturalWidth>=600) || /workspace-zb-cdn/i.test(s);
                if(clean && big) r.push({w:i.naturalWidth,h:i.naturalHeight,src:s});
            });
            return r;
        }"""
    )


async def download_imgs(urls, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    ok = 0
    for i, u in enumerate(urls, 1):
        ext = "png"
        m = re.search(r"\.(png|jpe?g|webp|gif|bmp)(?:\?|$)", u, re.I)
        if m:
            ext = m.group(1).lower()
        fp = os.path.join(out_dir, f"qw_{i:02d}.{ext}")
        try:
            req = urllib.request.Request(u, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
                "Referer": "https://qianwen.com/",
            })
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()
            if len(data) > 1000:
                with open(fp, "wb") as f:
                    f.write(data)
                ok += 1
                log(f"  下载 {i}/{len(urls)} -> {fp} ({len(data)//1024}KB)")
            else:
                log(f"  ✗ {i} 下载过小，跳过")
        except Exception as e:
            log(f"  ✗ {i} 下载失败: {e}")
    return ok


async def wait_and_grab(page, out_dir, timeout=90, cooldown=30):
    before = await collect_clean_imgs(page)
    before_srcs = {x["src"] for x in before}  # 生成前页面已有图（历史/装饰/头像）→ 必须排除
    waited = 0
    # 冷却：生成中先出 gradient 占位，至少等 cooldown 秒再开始认真抓
    await page.wait_for_timeout(cooldown * 1000)
    waited += cooldown
    while waited < timeout:
        await page.wait_for_timeout(2000)
        waited += 2
        imgs = await collect_clean_imgs(page)
        new = [x for x in imgs if x["src"] not in before_srcs]  # 只取本次新增（生成的 4 张）
        if new:
            # 再等一小会儿确保 4 张都渲染
            await page.wait_for_timeout(3000)
            imgs = await collect_clean_imgs(page)
            new = [x for x in imgs if x["src"] not in before_srcs]
            log(f"检测到 {len(new)} 张新生成原图（已排除生成前 {len(before)} 张历史/装饰图）")
            urls = [x["src"] for x in new]
            ok = await download_imgs(urls, out_dir)
            return {"count": len(new), "downloaded": ok, "urls": urls}
    imgs = await collect_clean_imgs(page)
    new = [x for x in imgs if x["src"] not in before_srcs]
    log("超时未检测到新原图（可能仍在生成或 UI 变化）")
    return {"count": len(new), "downloaded": 0, "urls": [x["src"] for x in new]}


async def do_generate(page, prompt, ref, ratio, out_dir, timeout):
    await enter_ai_image_mode(page)
    # 图生图：上传参考图
    if ref:
        if not os.path.exists(ref):
            log(f"✗ 参考图不存在: {ref}")
            return None
        try:
            async with page.expect_file_chooser(timeout=6000) as fc_info:
                # 优先 JS click 参考图按钮（绕 pointer-events），失败再走 get_by_text
                clicked = await js_click_by_text(page, "参考图")
                if not clicked:
                    await page.get_by_text("参考图").first.click(timeout=4000)
            fc = await fc_info.value
            await fc.set_files(ref)
            await page.wait_for_timeout(1200)
            log("已上传参考图:", os.path.basename(ref))
        except Exception as e:
            log("⚠️ 上传参考图失败:", e)
    # 填 prompt（contenteditable + 轮询完整性校验 + 确定性 React sync 等待）
    # 用户 2026-08-13 22:4x 诊断：loc.fill / insert_text 触发 React 受控组件 onChange 后，
    # React state 异步合并（React 18 batching）。如果紧跟 click send，会提交"旧 state"
    # （空/上轮残留），而 DOM 显示"新值"——典型"前半部分发了、Negative 段停留"现象。
    box = page.locator('[contenteditable="true"]').first
    await box.click()
    # 用 locator.fill 替代 insert_text（Playwright 走 React 兼容路径更稳）
    await box.fill("")
    await page.wait_for_timeout(200)
    await box.fill(prompt)
    # 等 React merge input event 进 state（轮询读回对比，最多 3 秒）
    expect_norm = " ".join(prompt.split())
    for _ in range(15):
        cur = await page.evaluate("(s)=>{const e=document.querySelector(s);return e? (e.innerText||e.textContent||''):''}", '[contenteditable="true"]')
        if " ".join((cur or "").split()) == expect_norm:
            break
        await page.wait_for_timeout(200)
    else:
        log(f"⚠️ 完整性校验未通过：期望 {len(expect_norm)} 字符，读回 {len(' '.join(cur.split())) if cur else 0} 字符（继续发送，发送前已轮询 3 秒）")
    # 确定性 React state sync 等待（关键修复：不能再赌随机延时）
    await page.wait_for_timeout(1500)
    # 比例（UI 控件，必做）
    if ratio:
        await set_ratio(page, ratio)
    # 发送
    try:
        await page.get_by_role("button", name="发送消息").click(timeout=6000, force=True)
        log("已点击发送")
    except Exception as e:
        log("✗ 发送失败:", e)
        return None
    return await wait_and_grab(page, out_dir, timeout=timeout)


async def check_login(page):
    await page.goto(QW_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(2500)
    has_login = await page.evaluate(
        "() => !!([...document.querySelectorAll('button, a')].find(e=>(e.innerText||'').trim()==='登录'))"
    )
    title = await page.title()
    log(f"页面标题: {title} | 检测到登录按钮: {has_login}")
    return not has_login


async def main():
    ap = argparse.ArgumentParser(description="千问 AI生图 确定性 CLI（CloakBrowser 隐身路线）")
    ap.add_argument("--prompt", help="生图 prompt 文本")
    ap.add_argument("--ref", help="参考图路径（图生图）")
    ap.add_argument("--ratio", default="1:1", help="比例控件：9:16/3:4/1:1/4:3/16:9（默认 1:1）")
    ap.add_argument("--out", default="./qwen_gen_out", help="下载目录")
    ap.add_argument("--timeout", type=int, default=90, help="生成轮询超时（秒）")
    ap.add_argument("--headless", action="store_true", help="无头模式（默认有头，便于登录/过滑块）")
    ap.add_argument("--login", action="store_true", help="有头窗口仅登录，登完自动关闭")
    ap.add_argument("--check", action="store_true", help="只读探测登录态，不生成")
    ap.add_argument("--harvest", action="store_true", help="整页收割：不生成，下载当前页已渲染无水印原图")
    o = ap.parse_args()

    bin_path = get_cloak_bin()
    if not os.path.exists(bin_path):
        log(f"✗ 未找到 CloakBrowser 隐身二进制: {bin_path}\n请先运行 cloakbrowser install / doctor")
        sys.exit(1)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            PROFILE, headless=o.headless, executable_path=bin_path,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            if o.login or o.check:
                await page.goto(QW_URL, wait_until="domcontentloaded")
                await page.wait_for_timeout(2500)
                if o.check:
                    logged = await check_login(page)
                    print(json.dumps({"logged_in": logged}, ensure_ascii=False))
                    await ctx.close()
                    return
                # login 模式：有头等用户手登
                log("有头登录模式：请手动登录 / 过滑块，最多等 20 分钟。完成后关闭窗口或等待自动关闭。")
                await page.wait_for_timeout(20 * 60 * 1000)
                await ctx.close()
                log("登录窗口已关闭，profile 已持久化到", PROFILE)
                return

            # 生成 / 收割 前先验登录
            logged = await check_login(page)
            if not logged:
                log("✗ 未登录（检测到登录按钮）。请先运行: python qwen_gen.py --login")
                await ctx.close()
                sys.exit(2)

            if o.harvest:
                imgs = await collect_clean_imgs(page)
                log(f"整页收割：检测到 {len(imgs)} 张无水印原图")
                ok = await download_imgs([x["src"] for x in imgs], o.out)
                print(json.dumps({"harvested": len(imgs), "downloaded": ok}, ensure_ascii=False))
                await ctx.close()
                return

            if not o.prompt:
                log("✗ 请传入 --prompt")
                await ctx.close()
                sys.exit(1)

            # ★ 用户 2026-08-13 22:5x 强制要求：复用同 tab 起新任务，绝不开新 tab
            # 修前行为：每次跑都 launch_persistent_context → 新 Chrome + 新 tab，连跑多次本地内存涨。
            # 修后行为：复用现有 page，in-page 点 sidebar 的「新建对话」（HTTP fallback 在 start_new_chat_in_same_tab）。
            await start_new_chat_in_same_tab(page, log)

            result = await do_generate(page, o.prompt, o.ref, o.ratio, o.out, o.timeout)
            print(json.dumps(result, ensure_ascii=False))
        finally:
            try:
                await ctx.close()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
launch_cloak_qwen.py — 启动 CloakBrowser 隐身 Chromium 供 browser-qwen MCP 连接（A 路线）

用途：让既有的 `browser-qwen` MCP（mcp.json 里指向 127.0.0.1:9222）连上的是
【隐身二进制 + cloak-cdp-profile】，而不是标准 Chrome + cdp-profile-h（后者被千问风控标黑）。

为什么要它：SKILL.md 既定"浏览器只认 MCP"的铁律，但又要求反检测（坑 #12）。
本脚本把"隐身"这一层塞进 MCP 的底层浏览器，于是上层 MCP 流程一行不动、自然就 stealth 了。

用法：
  python launch_cloak_qwen.py            # 后台启动隐身 Chrome @9222，打开千问页
  python launch_cloak_qwen.py --headed   # 有头（首次登录 / 过滑块用），登完别关窗口
  python launch_cloak_qwen.py --stop     # 关闭 9222 上的浏览器

启动后，在 WorkBuddy 里正常用 mcp__browser_qwen__* 工具即可，全程隐身。
"""
import argparse
import re
import subprocess
import sys
import time

CLOAK = r"C:\Users\nicho\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe"
PROFILE = r"C:\Users\nicho\.workbuddy\chrome-profiles\cloak-cdp-profile"
PORT = 9222
QW_URL = "https://qianwen.com/chat"


def get_cloak_bin():
    if __import__("os").path.exists(CLOAK):
        return CLOAK
    try:
        out = subprocess.run(
            [r"C:\Users\nicho\.workbuddy\binaries\python\envs\default\Scripts\cloakbrowser", "info"],
            capture_output=True, text=True, timeout=30,
        ).stdout
        m = re.search(r"Binary:\s*(\S+)", out)
        if m and __import__("os").path.exists(m.group(1)):
            return m.group(1)
    except Exception:
        pass
    return CLOAK


def stop():
    # 通过 CDP 关闭
    try:
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
        c.request("GET", "/json/version")
        c.getresponse()
        c.request("GET", "/json/close")
        c.getresponse()
        print("已请求关闭 9222 上的浏览器")
    except Exception as e:
        print("关闭失败（可能未运行）:", e)


def launch(headed):
    bin_path = get_cloak_bin()
    if not __import__("os").path.exists(bin_path):
        print("✗ 未找到 CloakBrowser 隐身二进制:", bin_path, "\n请先 cloakbrowser install")
        sys.exit(1)
    args = [
        bin_path,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-dev-shm-usage",
    ]
    if not headed:
        args.append("--headless=new")
    args.append(QW_URL)
    print("启动隐身 Chrome @", PORT, "profile:", PROFILE)
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # 等 CDP 起来
    for _ in range(20):
        try:
            import http.client
            c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=2)
            c.request("GET", "/json/version")
            c.getresponse()
            print("✓ CDP 已就绪 @ http://127.0.0.1:%d" % PORT)
            print("现在可在 WorkBuddy 用 mcp__browser_qwen__* 工具（已隐身）")
            return
        except Exception:
            time.sleep(0.5)
    print("⚠️ CDP 未起来，请检查 CloakBrowser 是否可启动")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="有头模式（登录/过滑块用）")
    ap.add_argument("--stop", action="store_true", help="关闭 9222 浏览器")
    o = ap.parse_args()
    if o.stop:
        stop()
    else:
        launch(o.headed)

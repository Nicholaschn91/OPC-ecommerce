#!/usr/bin/env python3
"""Path 1: CDP image/* byte grab for watermark-free aistudio original.
Non-blocking capture: events only ENQUEUE a getResponseBody request; the
unified read loop saves bodies when their response arrives (no nested waits,
so sibling responses are never swallowed). Captures image/* from Run through
Download (download fetch is the likely clean-original source)."""
import json, base64, time, sys, os, urllib.request, hashlib, re, argparse
import websocket

CDP = "127.0.0.1:9333"

parser = argparse.ArgumentParser(description='Path 1: CDP grab clean aistudio image')
parser.add_argument('prompt', nargs='?', default=None, help='generation prompt (plain text)')
parser.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "path1_out"),
                    help='output directory')
parser.add_argument('--prompt-file', '-f', help='read prompt from file (utf-8)')
parser.add_argument('--wait', type=int, default=35, help='seconds to wait for first generation (default 35)')
args = parser.parse_args()

OUT = args.out
os.makedirs(OUT, exist_ok=True)

if args.prompt_file:
    with open(args.prompt_file, 'r', encoding='utf-8') as f:
        raw_prompt = f.read()
elif args.prompt:
    raw_prompt = args.prompt
else:
    raw_prompt = (
        "A minimalist flat 2D vector illustration of a single red apple with a green leaf, "
        "centered on a pure white background, sage green and warm cream accent, clean editorial style."
    )
# Aspect ratio 保持 Auto：剥离 prompt 里的 --ar 令牌
PROMPT = re.sub(r'--ar\s+\S+', '', raw_prompt).strip()

class CDPClient:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self._id = 0
        self.images = []          # (url, bytes)
        self._capture = {}        # getResponseBody id -> url
        self._capturing = False

    def _next_id(self):
        self._id += 1
        return self._id

    def send(self, method, params=None):
        mid = self._next_id()
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        return mid

    def _save_body(self, result, url):
        if not result:
            return
        body = result.get("body", "")
        if not body:
            return
        data = base64.b64decode(body) if result.get("base64Encoded") else body.encode()
        if data:
            self.images.append((url, data))
            print(f"[capture] {len(data)}B {url[:70]}")

    def _handle_event(self, msg):
        if msg.get("method") == "Network.responseReceived":
            resp = msg["params"]["response"]
            mt = resp.get("mimeType", "")
            url = resp.get("url", "")
            if self._capturing and mt.startswith("image") and "zero-state" not in url:
                rid = msg["params"]["requestId"]
                cid = self.send("Network.getResponseBody", {"requestId": rid})
                self._capture[cid] = url

    def _dispatch(self, msg):
        if "id" in msg and msg["id"] in self._capture:
            url = self._capture.pop(msg["id"])
            self._save_body(msg.get("result"), url)
            return True
        if "method" in msg:
            self._handle_event(msg)
            return True
        return False

    def send_and_wait(self, method, params=None, timeout=60):
        mid = self.send(method, params)
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if "id" in msg and msg["id"] == mid:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} error: {msg['error']}")
                return msg.get("result", {})
            self._dispatch(msg)
        raise TimeoutError(f"no response for {method}")

    def evaluate(self, expr, timeout=40):
        e = expr.strip()
        if e.startswith("() =>"):
            e = "(" + e + ")()"
        r = self.send_and_wait("Runtime.evaluate",
                               {"expression": e, "returnByValue": True, "awaitPromise": True},
                               timeout=timeout)
        if "exceptionDetails" in r:
            raise RuntimeError(f"eval exception: {r['exceptionDetails']}")
        return r.get("result", {}).get("value")

    def call(self, method, params=None, timeout=60):
        return self.send_and_wait(method, params, timeout)

def jss(s):
    return json.dumps(s)

def open_aistudio_tab(cdp):
    ver = json.load(urllib.request.urlopen(f"http://{cdp}/json/version", timeout=10))
    bws = ver["webSocketDebuggerUrl"]
    ws = websocket.create_connection(bws, timeout=20)
    ws.send(json.dumps({"id": 1, "method": "Target.createTarget",
                        "params": {"url": "https://aistudio.google.com/prompts/new_chat?model=gemini-3.1-flash-lite-image"}}))
    tid = None
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == 1:
            tid = m.get("result", {}).get("targetId"); break
    ws.close()
    targets = json.load(urllib.request.urlopen(f"http://{cdp}/json", timeout=10))
    for t in targets:
        if t.get("targetId") == tid and t.get("webSocketDebuggerUrl"):
            return t
    return None

def main():
    targets = json.load(urllib.request.urlopen(f"http://{CDP}/json", timeout=10))
    page = None
    for t in targets:
        if t.get("type") == "page" and "aistudio.google.com" in t.get("url", ""):
            page = t; break
    if not page:
        print("NO_AISTUDIO_TAB -> creating one")
        page = open_aistudio_tab(CDP)
    if not page:
        print("page"); sys.exit(1)
    print("tab:", page["url"][:80])
    ws_url = page["webSocketDebuggerUrl"]

    c = CDPClient(ws_url)
    c.call("Network.enable")
    c.call("Runtime.enable")
    c.call("Page.enable")

    login = False
    for _ in range(20):
        try:
            login = c.evaluate("() => !!document.querySelector('textarea[aria-label=\"Enter a prompt\"]')")
        except Exception:
            login = False
        if login:
            break
        time.sleep(2)
    print("logged_in:", login)
    if not login:
        print("NOT_LOGGED_IN"); sys.exit(2)

    # fresh new_chat to reset state
    c.call("Page.navigate", {"url": "https://aistudio.google.com/prompts/new_chat?model=gemini-3.1-flash-lite-image"})
    time.sleep(6)
    login = c.evaluate("() => !!document.querySelector('textarea[aria-label=\"Enter a prompt\"]')")
    print("after-nav textarea:", login)

    r = c.evaluate("() => { const b=[...document.querySelectorAll('button')].find(x=>(x.textContent||'').includes('Images only')); if(b){b.click();return 'ON';} return 'NOBTN'; }")
    print("images_only:", r)
    time.sleep(1)

    fill = ("() => { const ta=document.querySelector('textarea[aria-label=\"Enter a prompt\"]');"
            " if(!ta) return 'NOTA';"
            " const s=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;"
            f" s.call(ta, {jss(PROMPT)});"
            " ta.dispatchEvent(new Event('input',{bubbles:true}));"
            " return 'SET:'+ta.value.length; }")
    print("fill:", c.evaluate(fill))
    time.sleep(2)

    run = ("() => { const bs=[...document.querySelectorAll('button')];"
           " let b=bs.find(x=>(x.textContent||'').trim().toLowerCase()==='run');"
           " if(!b) b=bs.find(x=>(x.textContent||'').toLowerCase().includes('run'));"
           " if(!b) b=bs.find(x=>(x.getAttribute('aria-label')||'').toLowerCase().includes('run'));"
           " if(b){b.click();return 'RUN:'+(b.textContent||'').trim().slice(0,20);}"
           " return 'NORUN:'+bs.map(x=>(x.textContent||'').trim()).filter(Boolean).slice(0,12).join('|'); }")
    print("run:", c.evaluate(run))

    # START capturing (generation + download fetches)
    c._capturing = True

    DETECT = ("() => { const turns=[...document.querySelectorAll('ms-chat-turn')];"
              " for(let i=0;i<turns.length;i++){ if(/an\\s+internal\\s+error\\s+has\\s+occurred/i.test(turns[i].textContent||'')){"
              " const r=[...turns[i].querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='Rerun this turn'||/rerun this turn/i.test(b.textContent||''));"
              " if(r) return 'ERROR_FOUND_RERUN_READY'; return 'ERROR_FOUND_NO_RERUN_BTN'; } } return 'NO_ERROR'; }")
    RERUN = ("() => { const turns=[...document.querySelectorAll('ms-chat-turn')];"
             " for(let i=0;i<turns.length;i++){ if(/an\\s+internal\\s+error\\s+has\\s+occurred/i.test(turns[i].textContent||'')){"
             " const r=[...turns[i].querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='Rerun this turn'||/rerun this turn/i.test(b.textContent||''));"
             " if(!r) return 'NO_RERUN';"
             " r.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,view:window}));"
             " r.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,cancelable:true,view:window}));"
             " r.click(); return 'RERUN_CLICKED'; } } return 'NO_ERROR_TURN'; }")
    VERIFY = ("() => { const img=[...document.querySelectorAll('img')].find(i=>(i.getAttribute('alt')||'').startsWith('Generated Image'));"
              " if(img) return 'OK_IMAGE';"
              " const turns=[...document.querySelectorAll('ms-chat-turn')];"
              " for(let t of turns) if(/an\\s+internal\\s+error\\s+has\\s+occurred/i.test(t.textContent||'')) return 'STILL_ERROR';"
              " return 'PENDING'; }")

    RATECHECK = ("() => { const txt=(document.body&&document.body.innerText)||'';"
                 " if(/rate\\s*limit|too many requests|try again later/i.test(txt)) return 'RATE_LIMITED';"
                 " return 'NO_RATE'; }")

    # poll generation up to --wait seconds
    final_state = "PENDING"
    deadline = time.time() + args.wait
    while time.time() < deadline:
        rc = c.evaluate(RATECHECK)
        if rc == "RATE_LIMITED":
            final_state = "RATE_LIMITED"
            print("[poll] rate limited - abort wait")
            break
        st = c.evaluate(DETECT)
        if st != "NO_ERROR":
            print("[poll] detect:", st)
            break
        vf = c.evaluate(VERIFY)
        if vf in ("OK_IMAGE", "STILL_ERROR"):
            final_state = vf
            print("[poll] verify:", vf)
            break
        time.sleep(5)
    else:
        print(f"[poll] no result after {args.wait}s")

    # if still pending/no-image, try Rerun on any internal error (up to 2 times)
    if final_state == "PENDING":
        for attempt in range(2):
            rc = c.evaluate(RATECHECK)
            if rc == "RATE_LIMITED":
                final_state = "RATE_LIMITED"
                print("[rerun] rate limited - abort retries")
                break
            st = c.evaluate(DETECT)
            if st == "NO_ERROR":
                vf = c.evaluate(VERIFY)
                if vf == "OK_IMAGE":
                    final_state = vf; break
                print(f"[rerun attempt {attempt}] still pending, no error button")
                time.sleep(8)
                continue
            if st == "ERROR_FOUND_RERUN_READY":
                print("rerun:", c.evaluate(RERUN))
                time.sleep(25)
                vf = c.evaluate(VERIFY)
                if vf == "OK_IMAGE":
                    final_state = vf; break
            else:
                print("unrecoverable:", st); break

    vf = final_state
    print("verify:", vf)
    if vf == "RATE_LIMITED":
        print("RESULT: RATE_LIMITED - free-tier cap hit; STOP and resume after window reset")
        sys.exit(10)

    # click Download to trigger clean-original fetch
    if vf == "OK_IMAGE":
        dl = ("() => { const bs=[...document.querySelectorAll('button')];"
              " let b=bs.find(x=>(x.textContent||'').trim().toLowerCase()==='download');"
              " if(!b) b=bs.find(x=>(x.textContent||'').toLowerCase().includes('download'));"
              " if(b){b.click();return 'DL:'+(b.textContent||'').trim().slice(0,20);} return 'NODL'; }")
        print("download:", c.evaluate(dl))
        time.sleep(8)

    # save captured network images
    print(f"captured image/* responses: {len(c.images)}")
    saved = []
    for i, (url, data) in enumerate(c.images):
        ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ("jpg" if data[:3] == b"\xff\xd8\xff" else "bin")
        sha = hashlib.sha256(data).hexdigest()[:12]
        fn = os.path.join(OUT, f"network_{i}_{sha}.{ext}")
        with open(fn, "wb") as f: f.write(data)
        saved.append((fn, len(data), sha, url))
        print(f"  saved {fn} ({len(data)}B) {url[:60]}")

    # grab DOM img for watermark comparison
    dom_src = c.evaluate("() => { const img=[...document.querySelectorAll('img')].find(i=>(i.getAttribute('alt')||'').startsWith('Generated Image')); return img?img.src:null; }")
    if dom_src and dom_src.startswith("data:image"):
        _, b64 = dom_src.split(",", 1)
        ddata = base64.b64decode(b64)
        dsha = hashlib.sha256(ddata).hexdigest()[:12]
        dfn = os.path.join(OUT, f"dom_{dsha}.{'png' if ddata[:8]==b'\x89PNG\r\n\x1a\n' else 'jpg'}")
        with open(dfn, "wb") as f: f.write(ddata)
        print(f"dom_img saved {dfn} ({len(ddata)}B) sha={dsha}")
        for fn, sz, sha, url in saved:
            print(f"  network sha={sha} vs dom sha={dsha} -> {'SAME(watermarked?)' if sha==dsha else 'DIFFERENT(likely clean)'}")
    else:
        print("dom_src:", str(dom_src)[:80], "(not a data URI)")

    if vf != "OK_IMAGE":
        diag = c.evaluate("() => { const t=[...document.querySelectorAll('ms-chat-turn')].map(x=>x.innerText).join('\\n'); const body=(document.body&&document.body.innerText)||''; const all=(t+'\\n---BODY---\\n'+body).slice(0,2000); return all + (all.length>=2000?'...':''); }")
        print("DIAG turns/body text:", diag)
        print("RATECHECK:", c.evaluate(RATECHECK))
    print("DONE")

if __name__ == "__main__":
    main()

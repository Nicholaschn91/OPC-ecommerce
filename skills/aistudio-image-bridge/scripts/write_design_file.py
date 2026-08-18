import sys, json, re
import feishu_products_io as F

SENTINELS = ("NO_RESPONSE_READY", "NO_CONTAINER", "NO_MARKER", "NO_SYS_BTN",
             "NO_COMBO", "NO_OPTION", "NO_TEXTAREA", "NO_RUN_BTN", "STILL_GENERATING")

# UI chrome tokens that leak into innerText when the model wraps VisualBridge
# prompts in code blocks (Material action buttons: copy / expand / etc.)
UI_TOKENS = {"code", "Text", "download", "content_copy", "expand_less",
             "expand_more", "copy_all", "visibility", "fullscreen",
             "thumb_up", "thumb_down", "info"}

def clean(text):
    # drop whole lines that are nothing but UI chrome tokens
    out = []
    for ln in text.split("\n"):
        if ln.strip() in UI_TOKENS:
            continue
        out.append(ln)
    text = "\n".join(out)
    # belt-and-suspenders: catch any residual inline tokens
    for tok in UI_TOKENS:
        text = text.replace("\n" + tok, "").replace(tok, "")
    # remove a stray "Response ready." if present
    text = text.replace("Response ready.", "").strip()
    # strip model's "（设计说明：…）" / "(设计说明: …)" commentary parentheticals — noise, not part of the VisualBridge prompt
    text = re.sub(r'（设计说明[：:].*?）', '', text, flags=re.DOTALL)
    text = re.sub(r'\(设计说明[：:].*?\)', '', text, flags=re.DOTALL)
    # tidy up blank lines left behind
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text

def is_valid(text):
    if not text:
        return False, "empty"
    if text.strip() in SENTINELS:
        return False, f"sentinel:{text.strip()}"
    if len(text) < 300:
        return False, f"too_short:{len(text)}"
    if "[" + "商品名称" + "]" in text:
        return False, "template_leak"
    if "【方向A" not in text and "【方向B" not in text:
        return False, "no_direction_marker"
    for k in ("Amazon_VisualBridge", "Etsy_VisualBridge", "eBay_VisualBridge"):
        if k not in text:
            return False, f"missing:{k}"
    return True, "ok"

def main():
    if len(sys.argv) < 3:
        print("usage: write_design_file.py <record_id> <design_file>")
        sys.exit(1)
    rid = sys.argv[1]
    path = sys.argv[2]
    with open(path, encoding="utf-8") as f:
        text = clean(f.read())
    ok, reason = is_valid(text)
    if not ok:
        print("REFUSED_WRITE reason=" + reason + " len=" + str(len(text)))
        sys.exit(2)
    T = F.get_token()
    r = F.update_design(T, rid, text)
    print("WROTE_LEN=" + str(len(text)))
    print(json.dumps(r, ensure_ascii=False))

if __name__ == "__main__":
    main()

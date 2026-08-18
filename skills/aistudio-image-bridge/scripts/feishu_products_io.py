import urllib.request, json, sys

# 飞书凭证从 references/config.json 读取（不入库，gitignored）
import os as _os, json as _json
def _load_feishu_cfg():
    _p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "references", "config.json")
    try:
        with open(_p, encoding="utf-8") as _f:
            return _json.load(_f)
    except FileNotFoundError:
        raise SystemExit(f"缺少飞书配置: {_p}\n请复制 references/config.example.json 为 config.json 并填入 APP_ID/APP_SECRET")
_CFG = _load_feishu_cfg()
APP_ID = _CFG["APP_ID"]
APP_SECRET = _CFG["APP_SECRET"]
APP_TOKEN = "ONy9bZ0oFaaiSEsf4ggcs61enRc"
TABLE_ID = "tbl75glY29VulRLm"

def api(method, url, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def get_token():
    tok = api("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
              body={"app_id": APP_ID, "app_secret": APP_SECRET})
    t = tok.get("tenant_access_token")
    if not t:
        raise SystemExit("TOKEN FAIL: " + json.dumps(tok, ensure_ascii=False))
    return t

def list_fields(token):
    fld = api("GET", f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/fields", token=token)
    return fld.get("data", {}).get("items", [])

def list_records(token, page_size=50):
    rec = api("GET", f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records?page_size={page_size}", token=token)
    return rec.get("data", {}).get("items", [])

def get_record(token, record_id):
    rec = api("GET", f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/{record_id}", token=token)
    return rec.get("data", {}).get("record", {})

def update_design(token, record_id, design_text):
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/{record_id}"
    return api("PUT", url, token=token, body={"fields": {"设计方案": design_text}})

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"
    T = get_token()
    if mode == "list":
        print("=== FIELDS ===")
        for f in list_fields(T):
            print(f.get("field_id"), "|", f.get("field_name"), "| type", f.get("type"))
        items = list_records(T)
        print(f"\n=== RECORDS ({len(items)}) ===")
        for it in items:
            fields = it.get("fields", {})
            name = fields.get("商品名称") or fields.get("商品ID") or "(no name)"
            rid = it.get("record_id")
            print(f"{rid} | {name}")
    elif mode == "show":
        rid = sys.argv[2]
        it = get_record(T, rid)
        print(json.dumps(it.get("fields", {}), ensure_ascii=False, indent=2))
    elif mode == "write":
        rid = sys.argv[2]
        text = sys.argv[3]
        print(json.dumps(update_design(T, rid, text), ensure_ascii=False, indent=2))

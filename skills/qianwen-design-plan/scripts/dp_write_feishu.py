import sys, re, json
sys.path.insert(0, "C:/Users/nicho/.workbuddy/skills/multi-agent-sop/aistudio-visualbridge/scripts")
import feishu_products_io as F

# 用法: dp_write_feishu.py <record_id> <raw_design_text>
# 直接吃 MCP 落盘的 raw innerText，做【传输层解码】（非内容清洗）后回写飞书「设计方案」字段。
#
# 为什么仍需解码（而非清洗）：
# v5.4 提示词自带「八、8.0 纯净输出协议」——模型输出已是 100% 纯英文、无寒暄/页脚/
# 思维链的结构化正文，故不再需要 extract_qianwen_output.py 做内容级清洗。
# 但 MCP 落盘的 innerText 仍是 JSON 字符串（换行被转义），必须还原成真实文本才能正确写入。
def load_raw_text(p):
    b = open(p, 'rb').read()
    s = b.decode('utf-8', errors='ignore').strip()
    # 情况1：整文件是 JSON 字符串（MCP 落盘 innerText 常为 JSON 包裹）→ json.loads 彻底解码
    if s.startswith('"') and s.endswith('"'):
        try:
            return json.loads(s)
        except Exception:
            pass
    # 情况2：非 JSON 包裹，但含字面转义序列（\n / \r，可能单/双重转义）→ 还原为真换行
    s = s.replace('\\\\n', '\n').replace('\\n', '\n')
    s = s.replace('\\\\r', '\r').replace('\\r', '\r')
    return s

rid = sys.argv[1]
src = sys.argv[2]
txt = load_raw_text(src)
# 去头部注释块（人工把关时可能加的 <!-- ... -->）
txt = re.sub(r'^<!--.*?-->\s*', '', txt, flags=re.S).strip()
T = F.get_token()
r = F.update_design(T, rid, txt)
print("FEISHU WRITE code:", r.get("code"), r.get("msg"))

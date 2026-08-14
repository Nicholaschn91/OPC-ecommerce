import sys, re
sys.path.insert(0, "C:/Users/nicho/.workbuddy/skills/multi-agent-sop/aistudio-visualbridge/scripts")
import feishu_products_io as F

# 用法: dp_write_feishu.py <record_id> <design_md>
# 去头部注释块后回写飞书「设计方案」字段
rid = sys.argv[1]
md = sys.argv[2]
txt = open(md, encoding='utf-8').read()
txt = re.sub(r'^<!--.*?-->\s*', '', txt, flags=re.S).strip()
T = F.get_token()
r = F.update_design(T, rid, txt)
print("FEISHU WRITE code:", r.get("code"), r.get("msg"))

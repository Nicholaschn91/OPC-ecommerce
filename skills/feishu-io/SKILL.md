# feishu-io Skill — 统一飞书多维表格读写

## 描述
OPC SOP 系统的唯一飞书读写入口。所有 Agent 通过本 skill 操作 Base A（输入）和 Base B（输出）。

## 触发词
- "读取飞书" / "写入飞书" / "创建记录" / "更新记录" / "查询记录"
- "发布事件" / "飞书回写"

## 核心配置

```yaml
# Base A — 采集输入
base_a:
  base_id: ONy9bZ0oFaaiSEsf4ggcs61enRc
  table_id: tbl75glY29VulRLm
  app_id: cli_a951353ba6b8dbcf

# Base B — Listing 输出
base_b:
  base_id: RP5ubb66waZnwDsc2MNcchcCnOb
  table_id: tblLku5v29ExnvtV
  app_id: cli_a951353ba6b8dbcf
```

## 环境变量

```env
# 来自飞书开放平台 -> 应用凭证
FEISHU_APP_ID=cli_a951353ba6b8dbcf
FEISHU_APP_SECRET=your-secret-here
```

## API 端点

```
# 获取 tenant access token
POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal

# 读取记录
GET  https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records

# 创建记录
POST https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records

# 更新记录
PUT  https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}

# 搜索记录
POST https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search
```

## 使用示例

```python
from skills.feishu_io.feishu_io import FeishuIO

# 初始化（默认 Base B）
feishu = FeishuIO(base="B")

# 读取数据（Base A）
spu_list = feishu.read_spurs()

# 创建父记录（Base B）
parent_id = feishu.create_parent_record(
    spu_id="SPU-001",
    product_name="Custom Wooden Cup Mat",
    data={
        "category": "Home & Kitchen",
        "direction": "eco-friendly",
        "variant_dimensions": "Color, Size"
    }
)

# 创建子记录
child_id = feishu.create_child_record(
    parent_id=parent_id,
    variant={"Color": "Natural", "Size": "Small"},
    data={
        "listing_title": "Handmade Wooden Cup Mat Natural Small",
        "bullet_points": [...],
        "image_urls": [...]
    }
)
```
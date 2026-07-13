# Base64 Encoder Skill

## 描述
Base64 编码/解码工具技能，用于图片转 Base64 Data URI、文件编码转换等基础编码操作。

## 触发词
- "base64编码"
- "base64解码"
- "图片转base64"
- "base64转图片"

## 核心能力
- 文件/字符串 Base64 编码
- Base64 字符串解码为文件
- 图片文件转 Data URI (`data:image/png;base64,...`)
- Data URI 解析还原文件
- 批量处理
- 字符集自动识别

## API 接口

### Python
```python
from skills.base64_encoder import Base64Encoder

encoder = Base64Encoder()

# 文件编码为 Base64
result = encoder.encode_file("image.png")
# result = "data:image/png;base64,iVBORw0KGgo..."

# Base64 解码为文件
encoder.decode_to_file("data:image/png;base64,iVBORw0KGgo...", "output.png")

# 字符串编码
encoded = encoder.encode_string("Hello World")
# "SGVsbG8gV29ybGQ="

# Base64 解码字符串
decoded = encoder.decode_string("SGVsbG8gV29ybGQ=")
# "Hello World"

# Data URI 解析
info = encoder.parse_data_uri("data:image/png;base64,iVBORw0KGgo...")
# {"mime": "image/png", "base64": "iVBORw0KGgo...", "size": 12345}

# 批量编码
results = encoder.batch_encode(["1.png", "2.jpg", "3.png"])
```

### CLI
```bash
# 编码文件
python -m skills.base64_encoder encode image.png

# 解码文件
python -m skills.base64_encoder decode "data:image/png;base64,..." output.png

# 字符串编码
python -m skills.base64_encoder encode-str "Hello World"

# 字符串解码
python -m skills.base64_encoder decode-str "SGVsbG8gV29ybGQ="

# 批量编码
python -m skills.base64_encoder batch images/ output.txt
```

## 核心参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input_path` | 必填 | 输入文件路径 |
| `output_path` | 可选 | 输出文件路径 |
| `mime_type` | 自动检测 | MIME 类型 |
| `data_uri` | True | 是否输出 Data URI 格式 |

## 输出格式
```json
{
  "success": true,
  "data_uri": "data:image/png;base64,iVBORw0KGgo...",
  "base64": "iVBORw0KGgo...",
  "mime_type": "image/png",
  "size_bytes": 245760
}
```

## 依赖
- Python 标准库 `base64`, `mimetypes`, `pathlib`

## 版本记录
| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-07-13 | 初版：Base64 编解码、Data URI 支持、批量处理 |
# Tabbit Upload Skill

## 描述
Tabbit 浏览器自动化上传技能，用于将生成的 Listing 内容自动上传到 Tabbit Chat 进行处理。

## 触发词
- "上传到Tabbit"
- "Tabbit上传"
- "发布到Tabbit"

## 核心能力
- 登录态管理：单实例 Chromium，需 `--remote-debugging-port=9222`
- 文件上传：支持图片/文档上传，使用 `expect_file_chooser`
- 额度监控：检测"本周用量已用完"，立即停止任务
- @菜单定位：`button:has(svg[class*="at-sign"])`

## 脚本路径
```
~/.workbuddy/skills/tabbit-upload/scripts/
├── tabbit_upload.py          # 主上传脚本
└── tabbit_browser.py         # 浏览器管理
```

## 关键规则
1. **单实例限制**：Tabbit 只能单实例运行，需复用现有浏览器实例
2. **登录态复用**：通过 `--remote-debugging-port=9222` 连接现有实例
3. **文件夹选择不可自动化**：文件上传支持 `expect_file_chooser`，但文件夹选择需人工
3. **额度用完即停**：检测到"本周用量已用完"立即停止，不重试
4. **@菜单定位**：使用 `button:has(svg[class*="at-sign"])` 定位 @提及按钮

## 环境变量
```env
TABBIT_BROWSER_PATH=C:\Users\nicho\AppData\Local\Tabbit\Application\Tabbit Browser.exe
TABBIT_DEBUG_PORT=9222
```

## 调用示例
```python
from skills.tabbit_upload import TabbitUploader

uploader = TabbitUploader()
result = uploader.upload_listing(
    listing_data={
        "title": "...",
        "bullets": [...],
        "description": "...",
        "images": ["path1.jpg", "path2.jpg"]
    },
    platform="amazon"
)
```
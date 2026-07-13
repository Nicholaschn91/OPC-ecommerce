# 本地自托管服务接入手册

> **位置**：`C:\Users\nicho\Desktop\1\`（源码/配置副本）
> **用途**：供 Agent 学习「如何配置与调用」；实际运行仍在本机原路径或 Docker 栈。

---

## 1. 9router — 本地 AI 路由代理

### 1.1 核心信息
| 项目 | 详情 |
|------|------|
| **源码** | `9router/`（`app/custom-server.js` 为入口） |
| **运行时数据** | `9router-runtime/`（含 provider 凭证、API Key、JWT 等） |
| **API 端点** | `http://localhost:20128/v1` (OpenAI 兼容) |
| **Dashboard** | `http://localhost:20128/dashboard` |
| **启动方式** | `node "9router/app/custom-server.js"`（官方 CLI 收到信号会 kill 服务） |
| **模型来源** | 连接 40+ 提供商（Kiro AI、OpenCode Free、OpenRouter 等） |

### 1.2 免费额度接入（必做）
Dashboard → **Providers** → 点击 **Connect**：
- **Kiro AI** (免费 Claude 无限)
- **OpenCode Free** (无需认证)
- 或自带 OpenRouter / Anthropic / OpenAI Key

### 1.3 Hermes 接入配置
```yaml
# ~/.hermes/config.yaml
custom_providers:
  9router:
    type: openai_compatible
    base_url: "http://localhost:20128/v1"
    api_key_env: "NINEROUTER_API_KEY"
    models:
      - "9router/auto"
      # Dashboard 里看到什么模型 ID 就填什么
```

```bash
# 设置环境变量
echo "NINEROUTER_API_KEY=your_key_from_dashboard" >> ~/.hermes/.env
hermes models refresh
```

### 1.4 关键提示
- **必须保持 9router 运行** — 它是本地服务，关了就没模型了
- **模型 ID 来自 9router** — 非标准 ID，如 `kr/claude-sonnet-4.5`、`opencode/gpt-4o`
- **免费模型需在 Dashboard 连接** — 先点 Connect Kiro AI / OpenCode Free
- **Windows 防火墙** — 首次运行可能弹窗允许网络访问，选"允许"

---

## 2. n8n — 工作流自动化

### 2.1 核心信息
| 项目 | 详情 |
|------|------|
| **源码** | `n8n/` |
| **运行时数据** | `n8n-data/` |
| **默认端口** | `http://localhost:5678` |
| **用途** | 复杂多步骤自动化、Webhook、定时任务、数据转换 |

### 2.2 启动
```bash
npx n8n
# 或 Docker
docker run -it --rm -p 5678:5678 -v ~/.n8n:/home/node/.n8n n8nio/n8n
```

### 2.3 Agent 集成点
- **Webhook 触发** — 供 Agent 发起流程
- **凭证管理** — 统一存储 API Key（飞书、Dify、Agnes 等）
- **错误重试/告警** — 内置重试策略、Slack/邮件告警

---

## 3. Dify — LLM 应用开发平台

### 3.1 核心信息
| 项目 | 详情 |
|------|------|
| **源码** | `dify/`（Docker Compose 栈） |
| **默认端口** | `http://localhost` (80) |
| **用途** | 合规检测、客服 Ada、自定义 Workflow/Chatflow |

### 3.2 部署
```bash
cd dify/docker
docker compose up -d
# 访问 http://localhost 完成初始化
```

### 3.2 关键应用（已落盘）
| 应用 | YAML 文件 | 用途 |
|------|-----------|------|
| **Listing 合规审核** | `skills/dify-compliance/dify_compliance_agent.yml` | 三层扫描、三级风险、飞书回写 |
| **智能客服 Ada** | `skills/dify-cs/dify_cs_agent.yml` | Amazon/eBay/Etsy 买家咨询、历史对话蒸馏 |

### 3.3 Agent 调用方式
```python
# Python 示例
import requests
resp = requests.post(
    "http://localhost/v1/chat-messages",  # 或 /v1/workflows/run
    headers={"Authorization": "Bearer {DIFY_API_KEY}"},
    json={"inputs": {...}, "response_mode": "blocking", "user": "boss-agent"}
)
```

### 3.4 知识库绑定
- 合规应用**必须**绑定 `risk_keywords.db` 导出的文档 + 平台政策文档
- 客服应用绑定 `cs_faq_distilled.md` + 产品手册

---

## 4. 1688-shopkeeper — 1688 选品铺货技能

### 4.1 核心信息
| 项目 | 详情 |
|------|------|
| **安装路径** | `~/.workbuddy/skills/1688-shopkeeper/` |
| **AK** | `EmLKR8uZHhz0JrOszlIgwoGtgUfTrAINCS04a5669f119bf000` (已配置) |
| **调用方式** | `python3 cli.py <command> ...` |

### 4.2 可用命令
| 命令 | 功能 |
|------|------|
| `search` | 关键词搜商品（支持渠道过滤：douyin/pdd/xiaohongshu/taobao） |
| `prod_detail` | 按商品 ID 批量获取详情（标题、价格、SKU、属性、商家） |
| `shops` | 查已绑定下游店铺 |
| `publish` | 一键铺货到抖店/拼多多/小红书/淘宝 |
| `opportunities` | 即时商机热榜 |
| `trend` | 类目/行业趋势与价格分布 |
| `shop_daily` | 店铺经营日报 |
| `configure` | 配置 AK |
| `check` | 检查配置状态 |

### 4.3 AK 获取
下载 [1688 AI版 APP](https://air.1688.com/kapp/1688-ai-app/pages/home?from=1688-shopkeeper) → 点「一键部署开店Claw」→ 复制 AK。

---

## 5. 服务依赖拓扑

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Hermes     │────▶│  9router    │◀───▶│ 免费 Provider│
│  (模型调用)  │     │  (本地代理)  │     │ (Kiro/OpenCode)│
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │
       ▼                   ▼
┌─────────────┐     ┌─────────────┐
│  Dify       │     │  n8n        │
│  (合规/客服) │     │  (工作流)    │
└─────────────┘     └─────────────┘
       │                   │
       ▼                   ▼
┌─────────────┐     ┌─────────────┐
│ 1688 Shopkeeper │   │ Agnes AI    │
│ (采集/铺货)      │   │ (图/视频生成) │
└─────────────┘     └─────────────┘
```

---

## 6. Bright Data CLI — 仅 4 个核心 API

> **注意**：Bright Data CLI 实际仅暴露以下 4 个产品 API，**没有**通用的 `brightdata scrape` 或 `brightdata crawl` 等通用命令。

| API | 核心能力 | 典型调用场景 |
|-----|----------|--------------|
| **Web Unlocker API** | 解锁反爬（验证码、JS 渲染、指纹绕过），返回干净 HTML/JSON | HiCustom/1688 详情页采集、竞品页面解锁 |
| **SERP API** | 搜索引擎结果页抓取（Google/Bing/Amazon/eBay 等），结构化 JSON 返回 | 关键词排名监控、竞品 ASIN 发现、类目关键词挖掘 |
| **Web Scraper API** | 通用网页抓取，支持自定义选择器、分页、登录态保持 | 列表页批量采集、自定义字段提取 |
| **Scraper Studio** | 可视化配置器，生成抓取任务模板，导出为 API 调用 | 复杂页面结构化、团队协作维护选择器 |

**调用方式**：均为 HTTP REST API，需在 Bright Data 控制台创建 Zone 获取 `zone` 与 `token`，Header 传 `Authorization: Bearer <token>`。

> ⚠️ **无**通用爬虫命令、`brightdata crawl`、`brightdata download` 等——仅以上 4 个 API 端点。

---

## 7. 常用操作速查

| 操作 | 命令 |
|------|------|
| 启动 9router | `node "C:\Users\nicho\AppData\Roaming\npm\node_modules\9router\app\custom-server.js"` |
| 启动 n8n | `npx n8n` |
| 启动 Dify | `cd C:\Users\nicho\Desktop\1\dify\docker && docker compose up -d` |
| 查看 9router 日志 | 终端直接输出 |
| 查看 n8n 执行记录 | `http://localhost:5678/executions` |
| 查看 Dify 日志 | `docker compose -f C:\Users\nicho\Desktop\1\dify\docker\docker-compose.yml logs -f` |
| 重启全部 | 依次重启上述三个服务 |

---

## 8. 环境变量汇总

```bash
# ~/.hermes/.env
NINEROUTER_API_KEY=9r_xxxxx
DIFY_API_KEY=app-xxxxx
FEISHU_APP_ID=cli_a951353ba6b8dbcf
FEISHU_APP_SECRET=your_feishu_app_secret_here
AGNES_API_KEY=sk-xxxxx
BRIGHTDATA_API_KEY=your_brightdata_key_here
```

---

*本文档为 Agent 只读参考，实际服务管理由用户手动控制。*
# Agent 对话窗口创建指南

## 问题
你创建的 Hermes 对话窗口（Session Agent）是独立的，它们不知道：
1. 自己是谁（身份）
2. Boss Agent 是谁
3. 项目路径在哪里
4. 其他 Agent 的存在

## 解决方案

### 方法 1：通过 Hermes Desktop 创建项目锚定的对话（推荐）

1. 在 Hermes Desktop 中，点击 **"New Project"**
2. 项目名称：`AgentName`（如 `Scraper Agent`）
3. 路径：`C:\Users\nicho\OPC_ecommerce`
4. 创建后，该对话会自动加载：
   - `C:\Users\nicho\OPC_ecommerce\.hermes.md`（项目上下文）
   - 对应的 `agents/agentname/AGENT.md`（通过 skill 加载）

### 方法 2：手动加载 AGENT.md 作为 System Prompt

1. 创建新的 Hermes 对话
2. 在对话开始时，发送以下内容作为 System Prompt：

```
你是 OPC 系统中的 [AgentName] Agent。

你的身份：
[复制对应 agents/[agentname]/AGENT.md 的内容]

你的工作空间：C:\Users\nicho\OPC_ecommerce
你的上级：Boss Agent（主控 Orchestrator）
你的下游：[根据 AGENT_REGISTRY.md 填写]

请确认你已理解自己的身份和职责。
```

### 方法 3：使用 Hermes Profile 隔离

1. 为每个 Agent 创建独立的 Hermes Profile
2. 每个 Profile 加载不同的 skill 和 system prompt
3. 缺点：配置复杂，不推荐

## 推荐做法

**使用方法 1**：每个 Agent 一个 Project，锚定到 OPC_ecommerce 目录。

这样每个 Agent 对话窗口都能：
- 自动加载 `.hermes.md`（项目上下文）
- 访问 `agents/*/AGENT.md`（通过 skill_view）
- 知道 Boss Agent 是谁（在 `.hermes.md` 中定义）
- 知道数据源（飞书 Base B）

## 需要创建的 Agent 对话窗口

| Agent | Project 名称 | 对应目录 |
|-------|-------------|----------|
| Boss | Boss Agent | agents/boss/ |
| Scraper | Scraper Agent | agents/scraper/ |
| Keyword Grader | Keyword Grader Agent | agents/keyword-grader/ |
| Router | Router Agent | agents/router/ |
| SEO | SEO Agent | agents/seo/ |
| Visual | Visual Agent | agents/visual/ |
| Dify Compliance | Dify Compliance Agent | agents/dify-compliance/ |
| Ads | Ads Agent | agents/ads/ |
| CS | CS Agent | agents/cs/ |
| Image Post-Processor | Image Post-Processor Agent | agents/image-post-processor/ |

# handoff/ — 异步交接区

> 用途：Agent 之间**不靠口述、信息自交换**。你留在这里的东西，对方来读；你不口述，对方不猜。

## 规则

1. **写入格式**：`handoff/<日期>-<主题>.md`，开头写明：
   - 来自（哪个 Agent）
   - 交给（哪个 Agent）
   - 要做什么 / 已做到哪
   - 阻塞点 / 需要对方确认的事
2. **只写自己名下产出**，不要替别人改文件。
3. **读方处理完**后，在原文件末尾追加 `## 处理结果`（谁、何时、结论）。
4. 交接不等同于推送——handoff 是**过程留痕**，最终改动仍按 OPERATIONS.md 走 git。
5. 敏感信息（密钥、token）**绝不**写进 handoff，只写"已配置到 X 文件，路径见 references"。

## 模板

```markdown
# 2026-08-14-关键词库重构
- 来自：home-workbuddy
- 交给：office-workbuddy
- 背景：关键词 T1-T5 分级需按新口径重排
- 要做的：在 skills/keyword-tier-resync/ 下跑 resync，只动 keyword_database.db
- 阻塞：需你确认是否先 pull 最新库再跑
- 处理结果：（对方填）
```

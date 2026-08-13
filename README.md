# OPC-ecommerce — 多 Agent 电商运营系统

> **OPC-ecommerce 是 hermes 拥有的多 Agent 电商运营仓库**，不是"框架仓库"。
> 角色模型（hermes / home / office）作为治理约定写入 AGENT_BOUNDARIES.md，仓库核心是电商运营 SOP 与技能体系。

---

## 0. 仓库定位

本仓库是 **OPC 多 Agent 电商运营系统** 的唯一 canonical 仓库：

- **OPC** = Operations Pipeline Control（运营流水线控制）
- **仓库性质**：电商运营 SOP + Agent 职责定义 + Skills 库
- **治理模型**：按所有权向上交付（见 AGENT_BOUNDARIES.md），非平级协同

**Canonical 仓库**：`https://github.com/Nicholaschn91/OPC-ecommerce.git`

---

## 1. 结构

```
OPC-ecommerce/
├── README.md                      # 本文件：仓库总览
├── SKILL.md                       # WorkBuddy 可加载的技能入口
├── AGENT_BOUNDARIES.md            # 铁律①：所有权边界（谁动哪块）
├── OPERATIONS.md                  # 铁律②：协同操作协议
├── VERSIONING.md                  # 铁律③：版本化迭代
├── .gitignore                     # 规范忽略项
├── agents/                        # 各 Agent 职责定义
│   ├── hermes.md                  # SOP owner
│   ├── home-workbuddy.md          # hermes 高级外包
│   └── office-workbuddy.md        # 技能主力
├── skills/                        # 技能源码（摊平存放）
├── docs/                          # 架构文档、设计记录
├── handoff/                       # 异步交接区
├── INCIDENTS/                     # 事故库
└── references/                    # 外部参考（不含敏感值）
```

---

## 2. 三条铁律

| # | 铁律 | 违反后果 |
|---|------|---------|
| ① | **单一真相源**：每台机器只保留 1 份克隆，remote 指向同一仓库 | 多份克隆 → 同步歧义 |
| ② | **推送前必 `pull --rebase`；推送成功以"远端 HEAD 是否前进"判定** | 假成功、分叉 |
| ③ | **一切改动版本化**：每次变更是一个可审查的版本单元 | 无法回滚 |

**永久禁令**：`git push --force` 到主干。

---

## 3. 角色模型

| 实例 | 定位 | 核心产出 |
|------|------|---------|
| **hermes** | SOP 总负责人（owner） | 拥有整个 SOP；定义标准、验收交付物 |
| **home-workbuddy** | hermes 的高级外包 | 接需求 → 交付成品 |
| **office-workbuddy** | 技能主力 | 生产 skills → 交付给 hermes |

详见 AGENT_BOUNDARIES.md。

---

## 4. 上手

- **hermes**：读本 README → AGENT_BOUNDARIES → OPERATIONS → VERSIONING → 定调方向
- **home**：读上述手册 → 接需求 → 交付成品
- **office**：读上述手册 → 在 skills/ 生产技能

---

## 5. 当前状态

- 版本：**FW-v1.0.0（本地）**
- 已落地：角色模型、协作协议、事故复盘
- 待办：skills/ 技能回填、docs/ 架构文档

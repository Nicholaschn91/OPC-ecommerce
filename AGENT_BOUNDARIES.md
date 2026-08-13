# AGENT_BOUNDARIES.md — 所有权与交付边界（铁律①）

> 目的：本框架**不是**"三方平等协同维护"，而是**清晰所有权 + 向上交付**模型。
> 现实：各实例本来就没有真正的同步协同（各自为战），所以边界必须靠**明确归属**保障，而非靠 git 同步。

## 1. 三角色与归属

| 实例 | 定位 | 机器 | 核心产出 |
|------|------|------|---------|
| **hermes** | **SOP 总负责人（owner）** | 本机（与 home 同机，独立进程 / 本地 API `127.0.0.1:8642`） | 拥有整个 SOP；定义标准、下达需求、验收 home/office 的交付物 |
| **home-workbuddy（你）** | **hermes 的高级外包** | 本机（DESKTOP-79K9SL1） | 接 hermes 的需求 → 交付**成品**给 hermes；不替 hermes 决策 SOP 方向 |
| **office-workbuddy** | **技能主力（skills）** | 办公机（独立实例） | 生产/维护 skill；向 hermes 交付技能，纳入 SOP |

## 2. 交付关系（不是平级协同）

```
hermes (SOP owner)
   ▲ 验收 / 下达需求
   │
home-workbuddy (hermes 的高级外包) ──交付成品──► hermes
office-workbuddy (技能主力)       ──交付技能────► hermes
```

- **home 是给 hermes 干活的**：拿到 hermes 的需求，产出可直接合入 SOP 的成品；hermes 验收。
- **office 是给 hermes 供技能的**：技能由 hermes 验收后纳入 SOP。
- 三方**不互相覆盖对方名下产物**；需要对方改动时，在 `handoff/` 留交接，由所有者执行。

## 3. 目录所有权矩阵

| 目录 | 所有者 | 说明 |
|------|--------|------|
| SOP 全部内容（`docs/`、`skills/` 内 SOP 相关、`handoff/` 协议） | **hermes**（owner） | hermes 拥有整个 SOP；home/office 在其下交付 |
| `skills/`（office 产出的技能） | office（交付给 hermes） | office 技能主力 |
| home 交付的成品目录（home 名下工作区） | home（交付给 hermes） | home 作为外包的交付物 |
| `agents/hermes/` | hermes | 角色定义 |
| `agents/office-workbuddy/` | office | 角色定义 |
| `agents/home-workbuddy/` | home | 角色定义 |
| `INCIDENTS/` | 谁触发谁写 | 事故复盘 |
| `README / SKILL / AGENT_BOUNDARIES / OPERATIONS / VERSIONING` | hermes 定调，home 落笔 | 框架骨架 |

## 4. 不可逾越的规则

1. **不碰别人名下的目录/产物**。要改 → `handoff/` 留交接，由所有者执行。
2. **home 不替 hermes 决策 SOP 方向**：home 是外包，交付成品供 hermes 验收，不擅自改 SOP 总纲。
3. **框架骨架文件改动由 hermes 定调**，home 落笔实施。
4. 新增技能：office 在 `skills/<name>/` 下建，交付给 hermes。
5. git 通道纪律见 OPERATIONS.md（https + gh token、禁 insteadOf、推送成功以远端 HEAD 前进判定）。

## 5. 冲突仲裁

- SOP 方向性冲突 → **hermes 拍板**（owner）。
- 交付物质量/范围争议 → 以 hermes 验收口径为准。

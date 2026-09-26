---
name: stats-bar
description: 查询 ZCode 会话用量统计（轮数/步数/LLM 与工具耗时/首 token 延迟/tok/s/缓存命中/token 用量）。触发词：会话用量、token 消耗、这个会话跑了多少、统计一下用量、stats、缓存命中率、tok/s。通过 mcp__stats-bar__* 工具读取，用户也可用 /stats 命令直查（同口径）。
---

# 会话用量统计（stats-bar）

用 `stats-bar` 插件查询当前或指定会话的用量。两个入口同口径（单一事实源 `compute.mjs`，`first_token_at` 口径）：

- **MCP 工具**：`mcp__stats-bar__*`（本技能主要用法）
- **/stats 命令**：用户直接输入 `/stats [session_id]`，适合一次性查询

## 工具

- `mcp__stats-bar__stats_session` — 查指定会话（`sessionId` 可选，留空返回最新会话）。返回 rounds/steps/llmMs/toolMs/avgTtft/throughput/cacheHit/inputTokens/outputTokens 等。
- `mcp__stats-bar__stats_latest` — 返回当前活动库最近更新的会话及其统计。
- `mcp__stats-bar__stats_schema` — 返回各字段口径说明（数据字典），用于解释"这个数字怎么算的"。

## 典型用法

1. 用户问"这个会话用了多少 token / 跑了多少轮"：调 `stats_session`（`sessionId` 传当前会话，留空即最新）；用户只是要一次结果时也可提示直接输 `/stats`。
2. 用户问"缓存命中率多少 / 为什么 tok/s 这么高"：先 `stats_session` 拿数，再 `stats_schema` 解释口径。

## 口径要点（详见 stats_schema）

- ttft 取 `first_token_at - started_at`，仅统计 `first_token_at` 非空行（`tool-calls` 响应无首 token，恒空）。
- throughput 分子分母集合对称（同为 `first_token_at` 非空且 `output_tokens>0` 行），避免高估。
- rounds 取 `turn_usage` 与 `model_usage` 的 distinct turn_id 较大者，兜底进行中回合。
- 多库时按 lastActivity 最大者选权威库，不合并。

## 边界

- 只读查询，不写任何数据。
- 数据源是 ZCode 的 `db.sqlite`（`C:\Users\<用户>\.zcode\cli\db\` 或 `dataBaseDir` 指定库），工作区路由 `<ws>/.zcode/cli/db/` 优先。
- 底部状态条由 asar 薄壳补丁交付：patch/elevate-install.cmd 提权安装（一次 UAC），ZCodeStatsBarSelfHeal 登录任务在 ZCode 更新后自动重打。MCP 工具与 /stats 完全独立于薄壳，薄壳失效只影响 bar 显示，不影响查数。

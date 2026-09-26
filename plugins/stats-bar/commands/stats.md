---
description: 查询当前（或指定）ZCode 会话的用量统计：轮数、步数、LLM/工具耗时、首 token 延迟、tok/s、缓存命中率、token 用量。
argument-hint: "[session_id，留空查最新会话]"
---

查询 ZCode 会话用量统计。数据一律来自 `mcp__stats-bar__*` 工具（口径与历史版本底部状态栏一致），禁止手工估算数字。

会话参数：$ARGUMENTS

步骤：

1. 调用 `mcp__stats-bar__stats_session`：上面参数是 `sess_` 开头的会话 id 时原样传入，否则不传 `sessionId`（返回最新会话）。
2. 若 MCP 工具不可用（未连接/未安装），提示用户到 **设置 → 插件管理** 检查 stats-bar 是否安装并启用，如实说明工具不可用，不要编造数字。
3. 按以下格式输出：
   - 首行一句话摘要：`<会话标题> · N 轮 / M 步 · 输入 X tok · 输出 Y tok`
   - 一张两列小表：LLM 总耗时、工具调用（次数+耗时）、平均首 token 延迟、解码吞吐（tok/s）、缓存命中率、ttft 覆盖度
   - 耗时超过 1 分钟用「x 分 y 秒」表述，token 数保留原始值。
4. 用户追问某个数字怎么算的，调 `mcp__stats-bar__stats_schema` 按口径解释，不要臆测。

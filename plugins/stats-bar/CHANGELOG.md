# stats-bar 更新日志

## 0.4.0 — 底部统计条回归（2026-09-26）

用户需求：会话界面直接看到 DSH StatsLine 式用量条（轮数/步数、LLM/工具耗时、
首 token、tok/s、缓存命中率、token 用量）。

点检证据（ZCode 0.16.9，`C:\Program Files\ZCode\resources\app.asar`，327MB/27068 条目）：
- 注入锚点 `out/host/index.js`、`out/renderer/index.html` **仍存在**，`apply` 实测可
  定位并成功构建 candidate——薄壳补丁在当前版本**结构上兼容**；
- 唯一障碍是权限与锁定：Program Files 写入需管理员，桌面端运行时 asar 被锁。
- 排查陷阱：不能字节 grep 在 asar 里搜平铺路径（头部是嵌套 JSON，必然零命中）；
  判断锚点用 `asarlib.header_prefix` / `read_entries`（按 `16+d` 精确读头部）。

变更：

- 新增 `patch/elevate-install.cmd` 一键提权安装：自弹 UAC → 校验 ZCode 已退出 →
  `apply --force`（自动备份）→ 注册最高权限登录任务 `ZCodeStatsBarSelfHeal`
  （此后 ZCode 更新免 UAC 自动重打）。
- SessionStart hook 回归但重新设计：`--session-check` 只检测不写 asar（Program
  Files 会话内提权不现实），缺失落 pending.flag；重打只发生在提权上下文（`--run`）。
- 检测毫秒级化：`asarlib.read_entries` 按头部索引只读两个注入目标的内容找哨兵，
  替代原来每次会话启动整读 327MB 的块扫描（头部损坏时仍回退旧路径）。
- `html_inject.js` 0.16.9 兼容保险：composer dock 锚点找不到时回退为窗口底部固定条；
  取不到会话 id 时显示库内最近会话并加「最近·」前缀（不谎报为当前会话），不再直接隐藏。
- `apply_patch.py` 写入遇 PermissionError 时给出明确指引（elevate-install.cmd）；
  ensure_patch 的 apply 子进程改用 `sys.executable`（计划任务环境 PATH 不可靠）。
- manifest 0.4.0：hooks 回归，描述改为「状态条 + /stats + MCP」三入口定位。

## 0.3.0 — 原生化改造（2026-09-26，同日被 0.4.0 部分回退）

- 新增 `commands/stats.md`（/stats 命令）；删除死资产 `patch/queries.json`、
  `patch/__pycache__/`；manifest 加 `commands`。
- 当时误判 asar「结构级不兼容」（平铺路径 grep 零所致），据此退役了 hook——
  0.4.0 实跑证伪后回归。详见 0.4.0 一节。

## 0.2.0 — 口径统一（2026-09-07）

- 新增 `compute.mjs` 单一事实源，MCP server 与薄壳 HTTP 服务共用，消除
  `queries.json` 与 `host_inject.js` 两处 SQL 的漂移。
- MCP 工具定型：`stats_session` / `stats_latest` / `stats_schema`。
- 新增 skills/stats-bar 技能与 SessionStart 薄壳自愈 hook（幂等、异常不阻塞）。
- 口径要点：ttft 取 `first_token_at - started_at`（不用覆盖率仅 ~78.5% 的派生列）；
  decode 分子分母集合对称；rounds 双源兜底；多库按 lastActivity 选权威库不合并。

## 0.1.0 — 首版（2026-09-04）

- asar 薄壳补丁：注入 stats HTTP 服务（127.0.0.1:45200）与底部状态栏脚本（3 秒轮询）。
- `apply_patch.py` 编排器：字节级 asar 补丁、备份保留 2 份、幂等、回滚。

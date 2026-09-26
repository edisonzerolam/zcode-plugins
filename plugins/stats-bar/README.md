# stats-bar

ZCode 会话用量统计插件：**DSH StatsLine 式底部状态条 + /stats 命令 + MCP 工具**，三入口同口径（单一事实源 `compute.mjs`）。

## 功能

**底部状态条**（会话界面输入区上方，3 秒轮询，单击刷新/双击隐藏）：

```
2 轮 · 46 步 | LLM 24m36s · 工具调用 23s | 首 token 8s · 41 tok/s | 缓存命中 96% | 输入 3.2M · 输出 46K
```

**/stats 命令**：聊天内直查当前（或指定）会话，附完整指标表。

**MCP 工具**（供 agent 调用）：`stats_session` / `stats_latest` / `stats_schema`（数据字典）。

指标：轮数 / 步数、LLM 总耗时、工具调用次数与耗时、平均首 token 延迟（TTFT）、解码吞吐（tok/s）、缓存命中率、输入 / 输出 token、ttft 覆盖度。

## 安装

### ① 底部状态条（asar 薄壳，一次性提权）

1. **完全退出 ZCode 桌面端**（含托盘图标）；
2. 双击 `patch/elevate-install.cmd`，UAC 点「是」——脚本自动打补丁（先备份）并注册最高权限登录自愈任务 `ZCodeStatsBarSelfHeal`；
3. 启动 ZCode，底部即出现状态条。

之后 ZCode 更新覆盖补丁时，登录任务会在下次登录自动重打（免 UAC）；插件安装时 SessionStart hook 也会毫秒级自检、缺失时落 pending 提醒。手动回滚：管理员控制台运行 `python patch/apply_patch.py restore`。

### ② 插件（/stats + MCP + 自检 hook）

在 **插件市场 → 添加 → 添加插件市场** 添加本插件所在的市场目录，安装 stats-bar。MCP 依赖系统 `node`（v22+，需内置 `node:sqlite`）。

## 工作原理

- `patch/apply_patch.py` + `asarlib.py` — 字节级 asar 补丁编排器（锚点头部预检、备份保留 2 份、幂等、回滚）；注入对象 `out/host/index.js`（stats HTTP 服务 127.0.0.1:45200）与 `out/renderer/index.html`（底部条脚本）。
- `patch/ensure_patch.py` — 自愈入口：`--session-check`（hook，只检测、毫秒级、落 pending）与 `--run`（提权登录任务，缺失即重打）。
- `patch/html_inject.js` — 状态条 UI：优先吸附 composer dock，DOM 变化时回退窗口底部固定条；会话 id 取不到时显示「最近·」最近会话（如实标注）。
- `compute.mjs` — 单一口径事实源，asar 内联副本与 MCP 共用。

## 数据口径

- ttft 取 `first_token_at - started_at`，仅统计非空行（`tool-calls` 响应无首 token）
- 吞吐分子分母集合对称（同为 `first_token_at` 非空且 `output_tokens>0` 行），避免高估
- rounds 取 `turn_usage` 与 `model_usage` 的 distinct turn_id 较大者，兜底进行中回合
- 多库时按 lastActivity 最大者选权威库，不合并

## 数据库定位

1. `ZCODE_STATS_DB_PATH` 环境变量
2. `<workspace>/.zcode/cli/db/db.sqlite`（工作区库优先）
3. `~/.zcode/cli/db/db.sqlite`（用户目录回退）

只读查询（`mode=ro`），不写任何数据。

## 版本说明

ZCode 0.16.x 起安装于 `C:\Program Files\ZCode`：asar 补丁**结构上兼容**（锚点仍在，2026-09-26 实测可构建 candidate），但写入需管理员且桌面端运行时锁定——这就是「一键提权安装 + 免 UAC 登录自愈任务」方案的原因。判断锚点存在性必须解析 asar 头部（嵌套 JSON），字节 grep 平铺路径必然零命中（0.3.0 曾因此误判）。

## 许可证

MIT

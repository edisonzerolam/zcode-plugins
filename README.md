# zcode-plugins

ZCode 社区插件市场。当前收录：

| 插件 | 版本 | 说明 |
|------|------|------|
| [stats-bar](plugins/stats-bar/README.md) | 0.4.0 | DSH StatsLine 式会话用量：底部统计条 + `/stats` 命令 + MCP 工具，三入口同口径（轮数/步数、LLM/工具耗时、首 token、tok/s、缓存命中率、token 用量） |

## 安装

在 ZCode **插件市场 → 添加 → 添加插件市场**，粘贴本仓库地址：

```
https://github.com/edisonzerolam/zcode-plugins
```

然后在市场中安装 **stats-bar**。安装后：

- **`/stats` 命令 + MCP 工具**：装完即用（MCP 依赖系统 `node` v22+，需内置 `node:sqlite`）。
- **底部统计条**（可选，Windows 专用）：通过 asar 薄壳补丁交付，需一次性管理员安装——完全退出 ZCode 桌面端后，双击运行 `plugins/stats-bar/patch/elevate-install.cmd`（自弹 UAC，自动打补丁并注册登录自愈任务 `ZCodeStatsBarSelfHeal`），重启 ZCode 生效；此后 ZCode 更新覆盖补丁时，登录任务在下次登录自动重打（免 UAC）。

> 风险披露：底部统计条通过字节级补丁修改 ZCode 桌面端 `app.asar`（注入 `out/host/index.js` 与 `out/renderer/index.html`），属实验性质，请自担风险。补丁前自动备份 2 份，管理员控制台运行 `python apply_patch.py restore` 可回滚。`/stats` 与 MCP 完全不涉及补丁，ZCode 更新不受影响。

## 结构

```
marketplace.json          # 市场清单
plugins/stats-bar/        # stats-bar 插件
```

## 贡献

新增插件请保持本仓库结构：`plugins/<name>/` 下放置 `.zcode-plugin/plugin.json` + 组件目录，并在 `marketplace.json` 的 `plugins` 数组追加条目。

# zcode-plugins

ZCode 社区插件市场。当前收录：

| 插件 | 版本 | 说明 |
|------|------|------|
| [stats-bar](plugins/stats-bar/README.md) | 0.1.0 | 底部用量统计条：会话轮数/步数、LLM/工具耗时、首 token、tok/s、缓存命中、token 用量 |

## 安装

在 ZCode **设置 → 插件管理 → 发现** 标签点击 **`+`**，添加本仓库：

```
https://github.com/edisonzerolam/zcode-plugins
```

然后在列表中点击 stats-bar 的 **获取** 安装。

> 注意：stats-bar 是薄壳补丁型插件，首次会话启动时会自动对 ZCode 桌面端 asar 打补丁（幂等，失效自动重打）。补丁修改 `app.asar` 字节，属实验性质，请自担风险。

## 结构

```
marketplace.json          # 市场清单
plugins/stats-bar/        # stats-bar 插件
```

## 贡献

新增插件请保持本仓库结构：`plugins/<name>/` 下放置 `.zcode-plugin/plugin.json` + 组件目录，并在 `marketplace.json` 的 `plugins` 数组追加条目。

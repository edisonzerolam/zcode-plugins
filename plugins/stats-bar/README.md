# stats-bar

ZCode 底部用量统计条插件：在输入框上方显示当前会话的实时用量统计，仿 DeepSeek Harness StatsLine。

## 功能

- 轮数 / 步数（rounds / steps）
- LLM 总耗时、工具调用总耗时
- 平均首 token 延迟
- 解码吞吐（tok/s）
- 缓存命中率
- 输入 / 输出 token 用量

单击刷新，双击隐藏。

## 安装

在 **设置 → 插件管理 → 发现** 中添加本插件所在的市场（本地目录 / Git URL / ZIP），然后点击 **获取** 安装。

安装后首次启动会话时，插件会自动对 ZCode 桌面端应用补丁（注入 stats HTTP 服务与底部栏脚本）。补丁失效时会在会话启动时自动重打（幂等，异常不阻塞）。

## 工作原理

本插件属于**薄壳补丁**型插件：

- `patch/host_inject.js` — 注入 `out/host/index.js`，启动一个本地 HTTP 服务（`127.0.0.1:45200`），从 ZCode 的 `db.sqlite` 读取 `model_usage` / `tool_usage` / `turn_usage` 表计算会话统计。
- `patch/html_inject.js` — 注入 `out/renderer/index.html`，在输入框上方渲染状态条，每 3 秒轮询一次。
- `patch/ensure_patch.py` — 会话启动时通过 `SessionStart` hook 检测补丁哨兵，失效自动重打。
- `patch/apply_patch.py` — asar 字节级补丁编排器（备份 / 幂等 / 回滚）。

## 数据库定位

插件自动探测 ZCode 会话数据库，按优先级：

1. `ZCODE_STATS_DB_PATH` 环境变量
2. `~/.zcode/v2/setting.json` 的 `dataBaseDir` 指向的数据库
3. `~/.zcode/cli/db/db.sqlite`（用户目录回退）

客户端会携带当前工作区路径（`?ws=` 参数），服务端据此精确定位工作区数据库，跨工作区统计不串数据。

## 开发

```bash
# 状态检查
python patch/apply_patch.py status

# 打补丁（桌面端需先退出）
python patch/apply_patch.py apply --force

# 回滚
python patch/apply_patch.py restore
```

## 许可证

MIT

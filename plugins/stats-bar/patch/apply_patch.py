#!/usr/bin/env python3
"""apply_patch.py — stats-bar 薄壳补丁器（编排层；字节操作在 asarlib）。

用法:
  python apply_patch.py status              检测补丁状态
  python apply_patch.py apply [--dry]       打补丁（--dry 只产出 candidate 不替换）
  python apply_patch.py restore             从最新备份回滚
  python apply_patch.py install-triggers    自举登录计划任务 + 用户级 SessionStart hook

补丁对象（2 个文件, 哨兵 ZC_STATS_BAR_PATCH_V1）:
  out/host/index.js                     追加 stats HTTP 服务（读 db.sqlite，算 session 统计）
  out/renderer/index.html               注入底部 bar 脚本（position:fixed; bottom:0）
安全约束: 桌面运行中拒绝替换（rename 探锁）；备份目录保留 2 份；锚点失配整体放弃。
注入文本存放在同目录 host_inject.js / html_inject.js，运行时读取。
注意: v0.3.0 起薄壳补丁退役为旧版手动方案——ZCode 0.16.x 装在 Program Files，
写入需管理员且须先关闭桌面端，SessionStart 自愈无法提权，故不再作为插件功能维护。
status/apply 先做 asar 头部预检：锚点缺失（结构不适用）时明确拒绝，不整读 asar。
本工具对 0.16.9 实测仍可定位锚点并构建 candidate（2026-09-26），手动打补丁仍可行。
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

import asarlib

SENTINEL = "ZC_STATS_BAR_PATCH_V1"
HERE = os.path.dirname(os.path.abspath(__file__))


def _find_asar():
    env = os.environ.get("ZCODE_ASAR_PATH")
    if env and os.path.isfile(env):
        return env
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\ZCode\resources\app.asar"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\zcode\resources\app.asar"),
        os.path.expandvars(r"%PROGRAMFILES%\ZCode\resources\app.asar"),
        os.path.expanduser(r"~\.zcode\resources\app.asar"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[0]


ASAR_PATH = os.path.realpath(_find_asar())
RES_DIR = os.path.dirname(ASAR_PATH)
PATCH_DIR = os.path.realpath(HERE)
LOG_PATH = os.path.realpath(os.path.join(HERE, "patch.log"))
CANDIDATE_PATH = os.path.realpath(os.path.join(HERE, "candidate.asar"))
BACKUP_FILE_NAME = "app.asar"
BACKUP_TS_PATTERN = r"^\d{8}-\d{6}$"
BACKUP_KEEP = 2

HOST_PATH = "out/host/index.js"
HTML_PATH = "out/renderer/index.html"
HTML_ANCHOR = "</body>"
HOST_INJECT_PATH = os.path.join(PATCH_DIR, "host_inject.js")
HTML_INJECT_PATH = os.path.join(PATCH_DIR, "html_inject.js")
COMPUTE_PATH = os.path.join(PATCH_DIR, "..", "compute.mjs")


def anchor_check():
    """廉价结构预检（只读头部）：返回 None=兼容（含锚点或头部损坏走全量路径）；返回字符串=不适用原因。

    asar 头部含全量文件清单，无需整读 300MB+ 即可判断锚点是否存在。
    """
    hdr = asarlib.header_prefix(ASAR_PATH)
    if hdr is None:
        return None  # 头部解析失败，交给原有全量路径给出精确报错
    paths = {p for p, _ in asarlib.walk_files(hdr)}
    missing = [p for p in (HOST_PATH, HTML_PATH) if p not in paths]
    if missing:
        return "asar 不含补丁锚点 {}：结构与薄壳补丁不适用（薄壳自 v0.3.0 退役为手动方案，插件功能请用 /stats 命令与 MCP 工具）".format(missing)
    return None


def read_inject(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def log(msg):
    line = "[{}] {}".format(datetime.datetime.now().isoformat(timespec="seconds"), msg)
    print(line)
    try:
        asarlib.append_text(LOG_PATH, line + "\n")
    except OSError:
        pass


def locate(data):
    hdr, cb, _ = asarlib.parse_header(data)
    by_path = {}
    for p, e in asarlib.walk_files(hdr):
        if "unpacked" in e:
            continue
        if p == HOST_PATH or p == HTML_PATH:
            by_path[p] = (e, asarlib.file_bytes(data, cb, e).decode("utf-8"))
    if HOST_PATH not in by_path:
        raise RuntimeError("host/index.js 定位失败")
    if HTML_PATH not in by_path:
        raise RuntimeError("index.html 定位失败")
    return hdr, cb, by_path


def strip_old_injects(src, kind):
    if kind == "host":
        src = re.sub(r"// ZC_STATS_BAR_PATCH_V[0-9]+ begin.*?// ZC_STATS_BAR_PATCH_V[0-9]+ end\n?", "", src, flags=re.S)
    elif kind == "html":
        src = re.sub(r"<script>/\*ZC_STATS_BAR_PATCH_V[0-9]+\*/.*?</script>", "", src, flags=re.S)
    return src


def new_contents(data, force=False):
    hdr, cb, by_path = locate(data)
    host_inject = read_inject(HOST_INJECT_PATH)
    # 把 compute.mjs 内容内联为兜底（asar 里 import 不到插件目录时用）。
    # compute.mjs 是 ESM：剥掉 import 行（其依赖在 host_inject 顶部已 import 同名别名）+ 去 export，
    # 包成 async IIFE 返回 { computeStats, QUERIES }，与 host_inject 的 loadCompute() 接口对齐。
    with open(COMPUTE_PATH, encoding="utf-8") as f:
        compute_src = f.read()
    body = "\n".join(
        ln for ln in compute_src.splitlines()
        if not ln.strip().startswith("import ")
    ).replace("export function", "function").replace("export { QUERIES };", "").replace("export const", "const")
    # 保险：剥掉任何残留的 export 关键字（防止将来 compute.mjs 加新导出时内联语法炸）
    body = body.replace("export ", "")
    # compute.mjs 的 import（DatabaseSync/join/createRequire）被剥掉后，在 IIFE 内补本地绑定，
    # 使内联副本自足（host_inject 顶部虽有同库 import，但别名不同、作用域在外，不能复用）。
    header = ("const { DatabaseSync } = await import('node:sqlite');\n"
              "const { join } = await import('node:path');\n"
              "const { createRequire } = await import('node:module');\n")
    body = header + body
    body = body.replace("const require = createRequire(import.meta.url);",
                        "const require = createRequire(import.meta.url);")
    inline_iife = "(async () => {\n" + body + "\nreturn { computeStats, QUERIES };\n})()"
    host_inject = host_inject.replace("/*__ZCSB_COMPUTE_INLINE__*/ null", inline_iife, 1)
    html_inject = read_inject(HTML_INJECT_PATH)
    patches = []
    src = by_path[HOST_PATH][1]
    if force:
        src = strip_old_injects(src, "host")
    elif SENTINEL in src:
        raise RuntimeError("host 已含哨兵")
    patches.append((HOST_PATH, (src + host_inject).encode("utf-8")))
    src = by_path[HTML_PATH][1]
    if force:
        src = strip_old_injects(src, "html")
    elif SENTINEL in src:
        raise RuntimeError("index.html 已含哨兵")
    if src.count(HTML_ANCHOR) != 1:
        raise RuntimeError("index.html </body> 锚点异常 (命中 {} 次)".format(src.count(HTML_ANCHOR)))
    patches.append((HTML_PATH, src.replace(HTML_ANCHOR, html_inject + HTML_ANCHOR, 1).encode("utf-8")))
    return patches


def cmd_status():
    reason = anchor_check()
    if reason:
        print("asar: {}".format(ASAR_PATH))
        print("薄壳补丁: 不适用 —— {}".format(reason))
        return 0
    data = asarlib.read_bytes(ASAR_PATH)
    print("asar: {}".format(ASAR_PATH))
    print("补丁状态: {}".format("已打补丁" if asarlib.contains(data, SENTINEL) else "未打补丁"))
    try:
        hdr, cb, _ = asarlib.parse_header(data)
        for p, e in asarlib.walk_files(hdr):
            if p == HOST_PATH:
                src = asarlib.file_bytes(data, cb, e).decode("utf-8", errors="replace")
                print("  host 路由: {}".format("已注入" if SENTINEL in src else "未注入"))
            if p == HTML_PATH:
                src = asarlib.file_bytes(data, cb, e).decode("utf-8", errors="replace")
                print("  脚本(index.html): {}".format("已注入" if SENTINEL in src else "未注入"))
    except Exception as e:
        print("解析异常: {}".format(e))
    return 0


def cmd_apply(dry, force=False):
    reason = anchor_check()
    if reason:
        print("拒绝: {}".format(reason))
        return 2
    data = asarlib.read_bytes(ASAR_PATH)
    if not force and asarlib.contains(data, SENTINEL):
        print("当前 asar 已打补丁，无需重复操作（如需重打请加 --force）")
        return 0
    patches = new_contents(data, force=force)
    cand, changed = asarlib.build_candidate(data, patches)
    n = asarlib.count_all_files(cand)
    n_orig = asarlib.count_all_files(data)
    hits = asarlib.sentinel_files(cand, SENTINEL.encode("utf-8"))
    if n != n_orig:
        raise RuntimeError("candidate 条目数 {}: 预期与原 asar 一致 {}".format(n, n_orig))
    if len(hits) != 2:
        raise RuntimeError("candidate 哨兵命中 {} 个文件（预期 2）".format(len(hits)))
    log("candidate 构建成功: {} 字节, {} 条目, 改动 {}".format(len(cand), n, changed))
    if dry:
        asarlib.write_bytes(CANDIDATE_PATH, cand)
        print("dry-run: candidate 已写入 {}".format(CANDIDATE_PATH))
        return 0
    if not asarlib.lock_probe(ASAR_PATH):
        print("拒绝: ZCode 桌面端正在运行（app.asar 被锁定）。请关闭后重试。")
        return 3
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        bd = asarlib.backup_dir(RES_DIR, ts, BACKUP_TS_PATTERN)
        asarlib.copy_file(ASAR_PATH, os.path.join(bd, BACKUP_FILE_NAME))
        asarlib.prune_backups(RES_DIR, BACKUP_TS_PATTERN, BACKUP_KEEP, BACKUP_FILE_NAME)
        asarlib.write_bytes(ASAR_PATH, cand)
    except PermissionError:
        log("写入被拒（{} 需管理员）".format(ASAR_PATH))
        print("拒绝: 写入 {} 需要管理员权限。请双击 patch/elevate-install.cmd（UAC 确认后自动完成）。".format(ASAR_PATH))
        return 4
    log("补丁已写入: 备份={} 改动={}".format(bd, changed))
    print("完成。备份: {}。重启 ZCode 后底部 bar 生效。".format(bd))
    return 0


def cmd_restore():
    bak = asarlib.newest_backup_file(RES_DIR, BACKUP_TS_PATTERN, BACKUP_FILE_NAME)
    if not bak:
        print("没有可用备份")
        return 1
    if not asarlib.lock_probe(ASAR_PATH):
        print("拒绝: ZCode 桌面端正在运行。请关闭后重试。")
        return 3
    asarlib.copy_file(bak, ASAR_PATH)
    log("已回滚到 {}".format(bak))
    print("已回滚: {}".format(bak))
    return 0


def cmd_install_triggers():
    sys.path.insert(0, PATCH_DIR)
    import install_triggers
    return install_triggers.main()


def main():
    # 不强制 stdout 编码：控制台场景交给 Python 原生控制台 API（GBK 控制台正常显示中文），
    # 管道场景跟随系统区域设置。强制 utf-8 在 cp936 控制台会输出乱码。
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description="stats-bar 薄壳补丁器")
    ap.add_argument("action", choices=["status", "apply", "restore", "install-triggers"])
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.action == "status":
        sys.exit(cmd_status())
    if args.action == "apply":
        sys.exit(cmd_apply(args.dry, args.force))
    if args.action == "restore":
        sys.exit(cmd_restore())
    if args.action == "install-triggers":
        sys.exit(cmd_install_triggers())


if __name__ == "__main__":
    main()

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
QUERIES_PATH = os.path.join(PATCH_DIR, "queries.json")


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
    with open(QUERIES_PATH, encoding="utf-8") as f:
        queries_json = f.read()
    host_inject = host_inject.replace("/*__ZCSB_QUERIES__*/ null", queries_json, 1)
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
    bd = asarlib.backup_dir(RES_DIR, ts, BACKUP_TS_PATTERN)
    asarlib.copy_file(ASAR_PATH, os.path.join(bd, BACKUP_FILE_NAME))
    asarlib.prune_backups(RES_DIR, BACKUP_TS_PATTERN, BACKUP_KEEP, BACKUP_FILE_NAME)
    asarlib.write_bytes(ASAR_PATH, cand)
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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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

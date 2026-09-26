#!/usr/bin/env python3
"""ensure_patch.py — stats-bar 薄壳自愈入口。

两种触发方式，权限语义不同：
  --session-check  SessionStart hook 调用：只检测，绝不写 asar。ZCode 0.16.x 装在
                   Program Files，会话内无法提权，补丁缺失时落 pending.flag 交给
                   登录自愈任务或手动 elevate-install.cmd 处理。
  --run            登录自愈任务（ZCodeStatsBarSelfHeal，/RL HIGHEST）或提权控制台
                   调用：检测缺失即重打（需 ZCode 桌面端已退出）。

检测为毫秒级：按 asar 头部索引只读 out/host/index.js 与 out/renderer/index.html
两个注入目标的内容找哨兵，不再整读 300MB+ 的文件体（头部损坏时回退旧的整块扫描）。
"""
import argparse
import datetime
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import asarlib  # noqa: E402

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
SENTINEL = b"ZC_STATS_BAR_PATCH_V1"
HOST_PATH = "out/host/index.js"
HTML_PATH = "out/renderer/index.html"
TARGETS = {HOST_PATH, HTML_PATH}
LOG_PATH = os.path.realpath(os.path.join(HERE, "patch.log"))
PENDING = os.path.realpath(os.path.join(HERE, "pending.flag"))
APPLY = os.path.realpath(os.path.join(HERE, "apply_patch.py"))
CHUNK = 8 * 1024 * 1024


def log(msg):
    line = "[{}] {}".format(datetime.datetime.now().isoformat(timespec="seconds"), msg)
    try:
        asarlib.append_text(LOG_PATH, line + "\n")
    except OSError:
        pass


def sentinel_ok(path):
    """旧整块扫描兜底：头部损坏时仍能判断哨兵是否存在。"""
    size = os.path.getsize(path)
    if size <= CHUNK:
        with open(path, "rb") as f:
            return SENTINEL in f.read()
    overlap = len(SENTINEL) - 1
    with open(path, "rb") as f:
        prev = b""
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                return False
            if SENTINEL in prev + chunk:
                return True
            prev = chunk[-overlap:]


def patch_state():
    """毫秒级状态检测：'patched' / 'missing' / 'incompatible'；头部损坏返回 None。"""
    entries = asarlib.read_entries(ASAR_PATH, TARGETS)
    if entries is None:
        return None
    if not entries:
        return "incompatible"
    return "patched" if any(SENTINEL in v for v in entries.values()) else "missing"


def remove_pending():
    try:
        os.remove(PENDING)
    except OSError:
        pass


def main():
    # 同 apply_patch.py：不强制 utf-8，避免 cp936 控制台乱码
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-check", action="store_true")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()
    try:
        if not os.path.isfile(ASAR_PATH):
            return 0
        state = patch_state()
        if state is None:
            state = "patched" if sentinel_ok(ASAR_PATH) else "missing"
        if state == "patched":
            if os.path.exists(PENDING):
                remove_pending()
                log("哨兵已恢复，清除 pending 标记")
            return 0
        if state == "incompatible":
            log("asar 无薄壳锚点，薄壳不适用，跳过")
            return 0
        # state == "missing"（未打补丁）
        if args.session_check:
            asarlib.write_text(PENDING, "pending")
            log("补丁缺失（{} 需管理员，会话内不重打），已落 pending；等待登录自愈任务或手动 elevate-install.cmd".format(ASAR_PATH))
            return 0
        # --run：提权上下文才走到这里
        if not asarlib.lock_probe(ASAR_PATH):
            asarlib.write_text(PENDING, "pending")
            log("桌面端运行中无法替换，已落 pending；将在下次登录任务/提权运行时重试")
            return 0
        r = subprocess.run([sys.executable, APPLY, "apply"], capture_output=True, text=True)
        ok = r.returncode == 0
        log("自愈结果: rc={} {}".format(r.returncode, (r.stdout or r.stderr or "").strip()[-200:]))
        if ok:
            remove_pending()
        return 0
    except Exception as e:
        log("ensure 异常(吞掉不阻塞): {}".format(e))
        return 0


if __name__ == "__main__":
    main()

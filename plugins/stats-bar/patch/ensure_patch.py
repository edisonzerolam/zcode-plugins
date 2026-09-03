#!/usr/bin/env python3
"""ensure_patch.py — stats-bar 薄壳自愈入口（SessionStart hook / 登录任务共用）。"""
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


def remove_pending():
    try:
        os.remove(PENDING)
    except OSError:
        pass


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-check", action="store_true")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()
    try:
        if not os.path.isfile(ASAR_PATH):
            return 0
        if sentinel_ok(ASAR_PATH):
            if os.path.exists(PENDING):
                remove_pending()
                log("哨兵已恢复，清除 pending 标记")
            return 0
        log("检测到补丁失效（哨兵缺失），尝试自愈")
        if not asarlib.lock_probe(ASAR_PATH):
            asarlib.write_text(PENDING, "pending")
            log("桌面端运行中无法替换，已落 pending；将在下次登录任务/会话自检时重试")
            return 0
        r = subprocess.run(["python", APPLY, "apply"], capture_output=True, text=True)
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

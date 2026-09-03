#!/usr/bin/env python3
"""install_triggers.py — 自举自愈触发器（幂等）。"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asarlib  # noqa: E402

PATCH_DIR = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
SELFHEAL_CMD = os.path.join(PATCH_DIR, "selfheal.cmd")
ENSURE = os.path.join(PATCH_DIR, "ensure_patch.py")
CFG_PATH = os.path.realpath(os.environ.get("ZCODE_CFG_PATH", os.path.expanduser(r"~\.zcode\cli\config.json")))
STARTUP_DIR = os.path.realpath(os.environ.get("ZCODE_STARTUP_DIR", os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")))
STARTUP_CMD = os.path.join(STARTUP_DIR, "stats-bar-selfheal.cmd")
STARTUP_BODY = ('@echo off\r\n'
                'cd /d "{patch_dir}"\r\n'
                'python ensure_patch.py --run\r\n').format(patch_dir=PATCH_DIR)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = []
    try:
        os.makedirs(STARTUP_DIR, exist_ok=True)
        asarlib.write_text(STARTUP_CMD, STARTUP_BODY)
        results.append(("启动文件夹自愈项", True, STARTUP_CMD))
    except OSError as e:
        results.append(("启动文件夹自愈项", False, str(e)[:120]))
    try:
        r = subprocess.run(["schtasks", "/Create", "/TN", "stats-bar-selfheal", "/SC", "ONLOGON",
                            "/TR", SELFHEAL_CMD, "/F"], capture_output=True,
                           encoding="utf-8", errors="replace")
        results.append(("计划任务(可选)", r.returncode == 0,
                        "已创建" if r.returncode == 0 else "需管理员权限，已由启动文件夹兜底"))
    except OSError as e:
        results.append(("计划任务(可选)", False, str(e)[:120]))
    with open(CFG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    hooks = cfg.setdefault("hooks", {})
    hooks["enabled"] = True
    ss = hooks.setdefault("events", {}).setdefault("SessionStart", [])
    cmd_args = ["python", ENSURE, "--session-check"]
    already = any(h.get("args") == cmd_args for blk in ss for h in blk.get("hooks", []))
    if not already:
        ss.append({"hooks": [{"type": "process", "command": "python", "args": cmd_args,
                              "timeoutMs": 20000, "statusMessage": "stats-bar 薄壳自检…"}]})
        asarlib.write_text(CFG_PATH, json.dumps(cfg, ensure_ascii=False, indent=2))
    results.append(("用户级 SessionStart hook", True, "已登记" if not already else "已存在"))
    for name, ok, detail in results:
        print("{}: {} {}".format(name, "OK" if ok else "FAIL", detail))
    return 0 if all(ok for _, ok, _ in results[:1] + results[2:]) else 1


if __name__ == "__main__":
    sys.exit(main())

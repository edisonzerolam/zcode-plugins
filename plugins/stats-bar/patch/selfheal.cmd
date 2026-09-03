@echo off
rem 从自身所在目录运行自愈入口（插件安装到任意位置均可）
cd /d "%~dp0"
python ensure_patch.py --run

@echo off
setlocal
cd /d "%~dp0"

rem stats-bar 一键提权安装：打 asar 补丁 + 注册登录自愈任务
rem 用法：完全退出 ZCode 桌面端后，双击本脚本，UAC 点"是"。
rem 注意：本文件必须保存为 GBK/ANSI 编码（本机 cmd 控制台为 cp936），不得转存 UTF-8。

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo [提权] 需要管理员权限，请在弹出的 UAC 窗口点"是"。
  powershell -NoProfile -Command "Start-Process cmd.exe -ArgumentList '/c','%~f0' -Verb RunAs"
  exit /b
)

tasklist /FI "IMAGENAME eq ZCode.exe" 2>nul | find /I "ZCode.exe" >nul
if %errorlevel% equ 0 (
  echo [拒绝] ZCode 桌面端正在运行，app.asar 被锁定。
  echo        请先完全退出 ZCode（含托盘图标），再重新运行本脚本。
  pause
  exit /b 1
)

set "PYTHON_EXE="
for /f "delims=" %%p in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%p"
if not defined PYTHON_EXE (
  echo [错误] 未找到 python。请先安装 Python 3 并加入 PATH。
  pause
  exit /b 1
)

echo [1/3] 打 asar 补丁（自动备份 2 份，可用 apply_patch.py restore 回滚）...
python "%~dp0apply_patch.py" apply --force
if %errorlevel% neq 0 (
  echo [失败] 打补丁未成功，见上方输出。
  pause
  exit /b 1
)

echo [2/3] 注册登录自愈计划任务（最高权限，之后 ZCode 更新免 UAC 自动重打）...
schtasks /Create /F /RL HIGHEST /SC ONLOGON /TN "ZCodeStatsBarSelfHeal" /TR "\"%PYTHON_EXE%\" \"%~dp0ensure_patch.py\" --run" >nul 2>&1
if %errorlevel% equ 0 (
  echo        已注册任务: ZCodeStatsBarSelfHeal
) else (
  echo        [警告] 注册失败（不影响本次补丁）；ZCode 更新后需手动重跑本脚本。
)

echo [3/3] 完成！启动 ZCode，会话界面底部将显示用量统计条。
echo        回滚: 管理员控制台运行 python "%~dp0apply_patch.py" restore
pause

@echo off
echo ============================================================
echo  Cookie Auto-Exporter Setup
echo  首次运行 - 需要你在浏览器中登录 YouTube 一次
echo ============================================================
echo.
echo 正在启动 Chromium 浏览器...
echo 请在打开的窗口中登录你的 YouTube 账号
echo.
py -3 cookie_playwright.py
echo.
if %ERRORLEVEL% EQU 0 (
    echo 成功! cookies.txt 已创建并验证通过
    echo 之后会自动运行，无需再次手动操作
) else (
    echo 请重试: py -3 cookie_playwright.py
)
pause

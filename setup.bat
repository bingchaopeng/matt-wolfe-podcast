@echo off
set PYTHON=C:\Users\30777\AppData\Local\Python\pythoncore-3.14-64\python.exe
set COOKIES=C:\Users\30777\matt-wolfe-podcast\cookies.txt
set TEST_URL=https://www.youtube.com/watch?v=nydHKXjwu0U
set PROJECT_DIR=C:\Users\30777\matt-wolfe-podcast

echo ===============================
echo Matt Wolfe Podcast - Setup
echo ===============================
echo.

if not exist "%PYTHON%" (
    echo Python not found
    pause
    exit /b 1
)

echo Step 1: Close Chrome and export cookies...
taskkill /f /im chrome.exe >nul 2>&1
timeout /t 2 /nobreak >nul

"%PYTHON%" -m yt_dlp --cookies-from-browser chrome --cookies "%COOKIES%" --skip-download --print title "%TEST_URL%"

if %ERRORLEVEL% NEQ 0 (
    echo Failed to export cookies.
    echo.
    echo Manual alternative:
    echo 1. Open Chrome, go to youtube.com and login
    echo 2. Install Get cookies.txt LOCALLY extension
    echo 3. Export cookies to %COOKIES%
    echo 4. Rerun this script
    pause
    exit /b 1
)

echo Cookies exported OK!
echo.

echo Step 2: Test pipeline...
cd /d "%PROJECT_DIR%"
"%PYTHON%" run.py dry-run

if %ERRORLEVEL% NEQ 0 (
    echo Test failed
    pause
    exit /b 1
)

echo ===============================
echo Setup complete!
echo Now run: install_task.bat for daily schedule
echo ===============================
pause
@echo off
set PYTHON=C:\Users\30777\AppData\Local\Python\pythoncore-3.14-64\python.exe
set SCRIPT=C:\Users\30777\matt-wolfe-podcast\run.py
set COOKIES=C:\Users\30777\matt-wolfe-podcast\cookies.txt
set TASK_NAME=MattWolfePodcast
set TASK_TIME=21:00

echo ===============================
echo Matt Wolfe Podcast - Schedule
echo ===============================
echo.

net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo This script needs administrator rights.
    echo Right-click and select Run as administrator.
    pause
    exit /b 1
)

if not exist "%PYTHON%" (
    echo Python not found: %PYTHON%
    pause
    exit /b 1
)

if not exist "%COOKIES%" (
    echo cookies.txt not found. Run setup.bat first.
    pause
    exit /b 1
)

echo Testing pipeline...
cd /d "C:\Users\30777\matt-wolfe-podcast"
"%PYTHON%" run.py dry-run
if %ERRORLEVEL% NEQ 0 (
    echo Test failed. Check output above.
    pause
    exit /b 1
)

echo.
echo Creating scheduled task (daily at %TASK_TIME%)...
schtasks /create /tn %TASK_NAME% /tr "\"%PYTHON%\" \"%SCRIPT%\" run" /sc daily /st %TASK_TIME% /f

if %ERRORLEVEL% EQU 0 (
    echo ===============================
    echo Task created successfully!
    echo Name: %TASK_NAME%
    echo Time: Daily at %TASK_TIME%
    echo.
    echo Manual run: schtasks /run /tn %TASK_NAME%
    echo Task mgr:   taskschd.msc
    echo Delete:     schtasks /delete /tn %TASK_NAME% /f
    echo ===============================
) else (
    echo Failed to create task. Run as administrator.
)

pause
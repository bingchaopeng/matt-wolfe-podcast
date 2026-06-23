@echo off
set "PROJECT_DIR=C:\Users\30777\matt-wolfe-podcast"
set "BAT_ENTRY=%PROJECT_DIR%\run.bat"
set "COOKIES=%PROJECT_DIR%\cookies.txt"
set TASK_NAME=MattWolfePodcast
set TASK_TIME=21:00

echo ===============================
echo AI Podcast - Windows Schedule
echo ===============================
echo.

net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo This script needs administrator rights.
    echo Right-click and select "Run as administrator".
    pause
    exit /b 1
)

if not exist "%BAT_ENTRY%" (
    echo run.bat not found: %BAT_ENTRY%
    pause
    exit /b 1
)

if not exist "%COOKIES%" (
    echo cookies.txt not found in %PROJECT_DIR%
    pause
    exit /b 1
)

echo Testing pipeline (dry-run)...
cd /d "%PROJECT_DIR%"
call "%BAT_ENTRY%" dry-run
if %ERRORLEVEL% NEQ 0 (
    echo Test failed. Check output above.
    pause
    exit /b 1
)

echo.
echo Creating scheduled task (daily at %TASK_TIME%)...
schtasks /create /tn %TASK_NAME% /tr "\"%BAT_ENTRY%\" run" /sc daily /st %TASK_TIME% /f /rl HIGHEST

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
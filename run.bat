@echo off
REM AI 播客 - 使用 CosyVoice venv Python 运行
setlocal
cd /d "%~dp0"
set "VENV_PYTHON=%~dp0.venv-cosyvoice\Scripts\python.exe"
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" run.py %*
) else (
    echo ERROR: CosyVoice venv not found at %VENV_PYTHON%
    echo Please ensure .venv-cosyvoice exists.
    exit /b 1
)

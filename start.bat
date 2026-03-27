@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================================
REM DailyReport - One-click startup script (Windows)
REM Optional: CLIProxyAPI proxy (if LLM_MODE=setup-token in .env)
REM ============================================================

REM --- Check .env ---
if not exist "%~dp0.env" (
    echo [ERROR] .env file not found. Creating from .env.example ...
    copy "%~dp0.env.example" "%~dp0.env"
    echo [INFO] Please edit .env to configure your settings, then re-run this script.
    pause
    exit /b 1
)

REM --- Read LLM config from .env ---
set LLM_PROVIDER=anthropic
set LLM_MODE=api-key
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
    set "key=%%A"
    echo !key! | findstr /b "#" >nul && (
        REM skip comment lines
    ) || (
        if "%%A"=="LLM_PROVIDER" set "LLM_PROVIDER=%%B"
        if "%%A"=="LLM_MODE" set "LLM_MODE=%%B"
    )
)

set ACTIVE_LLM_KEY=ANTHROPIC_API_KEY
if /I "%LLM_PROVIDER%"=="openai" set "ACTIVE_LLM_KEY=OPENAI_API_KEY"

echo ============================================
echo   DailyReport - Daily Intelligence System
echo   LLM Provider: %LLM_PROVIDER%
echo   LLM Mode: %LLM_MODE%
echo ============================================
echo.

REM --- Activate conda environment ---
call conda activate research_tools
if errorlevel 1 (
    echo [ERROR] Failed to activate conda env: research_tools
    echo Please ensure conda is installed and research_tools env exists
    pause
    exit /b 1
)
echo [OK] conda env research_tools activated
echo.

REM --- Start CLIProxyAPI if setup-token mode ---
if "%LLM_MODE%"=="setup-token" (
    echo [PROXY] Starting CLIProxyAPI on localhost:8317 ...
    if not exist "C:\cliproxyapi\cli-proxy-api.exe" (
        echo [ERROR] cli-proxy-api.exe not found at C:\cliproxyapi\cli-proxy-api.exe
        echo         Please make sure CLIProxyAPI is installed at C:\cliproxyapi\
        pause
        exit /b 1
    )
    start "CLIProxyAPI" cmd /c "C:\cliproxyapi\cli-proxy-api.exe --config C:\cliproxyapi\config.yaml 2>&1"
    timeout /t 2 /nobreak >nul
    echo [OK] CLIProxyAPI proxy started.
    echo.
) else (
    echo [PROXY] Skipping proxy (api-key mode, using %ACTIVE_LLM_KEY% directly)
    echo.
)

REM --- Check config/sources.yaml ---
if not exist "%~dp0config\sources.yaml" (
    echo [WARN] config/sources.yaml not found. Please copy:
    echo        copy config\sources.example.yaml config\sources.yaml
    echo.
)

REM --- Show commands ---
echo ============================================
echo Commands:
echo   python -m src.cli status                    Show system status
echo   python -m src.cli collect                   Collect today's data
echo   python -m src.cli report                    Generate overview report
echo   python -m src.cli deep-dive --items "1,2,3" Generate deep dive report
echo   python -m src.cli registry mark --id 20260325-001 --status star
echo                                              Mark a registry item as highly relevant
echo   python -m src.cli run                       Run full pipeline
echo ============================================
echo.

cmd /k

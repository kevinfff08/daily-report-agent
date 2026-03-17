@echo off
chcp 65001 >nul 2>&1
REM DailyReport startup script

echo ============================================
echo   DailyReport - Daily Intelligence System
echo ============================================
echo.

REM Activate conda environment
call conda activate research_tools
if errorlevel 1 (
    echo [ERROR] Failed to activate conda env: research_tools
    echo Please ensure conda is installed and research_tools env exists
    pause
    exit /b 1
)

echo [OK] conda env research_tools activated
echo.

REM Check .env file
if not exist "%~dp0.env" (
    echo [WARN] .env not found. Please copy and configure:
    echo        copy .env.example .env
    echo.
)

REM Check config/sources.yaml
if not exist "%~dp0config\sources.yaml" (
    echo [WARN] config/sources.yaml not found. Please copy:
    echo        copy config\sources.example.yaml config\sources.yaml
    echo.
)

REM Show help
python -m src.cli --help
echo.
echo ============================================
echo Commands:
echo   python -m src.cli status                    Show system status
echo   python -m src.cli collect                    Collect today's data
echo   python -m src.cli report                     Generate overview report
echo   python -m src.cli deep-dive --items "1,2,3"  Generate deep dive report
echo   python -m src.cli run                        Run full pipeline
echo ============================================
echo.

cmd /k

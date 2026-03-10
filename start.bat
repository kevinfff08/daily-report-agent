@echo off
REM DailyReport 启动脚本
REM 激活 conda 环境并显示帮助信息

echo ============================================
echo   DailyReport - 每日情报聚合系统
echo ============================================
echo.

REM 激活 conda 环境
call conda activate research_tools
if errorlevel 1 (
    echo [ERROR] 无法激活 conda 环境 research_tools
    echo 请确保已安装 conda 并创建了 research_tools 环境
    pause
    exit /b 1
)

echo [OK] conda 环境 research_tools 已激活
echo.

REM 检查 .env 文件
if not exist "%~dp0.env" (
    echo [WARN] 未找到 .env 文件，请复制 .env.example 并配置
    echo        copy .env.example .env
    echo.
)

REM 检查 config/sources.yaml
if not exist "%~dp0config\sources.yaml" (
    echo [WARN] 未找到 config/sources.yaml，请复制示例配置
    echo        copy config\sources.example.yaml config\sources.yaml
    echo.
)

REM 显示帮助
python -m src.cli --help
echo.
echo ============================================
echo 常用命令:
echo   python -m src.cli status                    查看系统状态
echo   python -m src.cli collect                    采集今日数据
echo   python -m src.cli report                     生成概览报告
echo   python -m src.cli deep-dive --items "1,2,3"  生成深度报告
echo   python -m src.cli run                        全流程执行
echo ============================================
echo.

cmd /k

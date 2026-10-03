@echo off
rem 后羿 HOUYI Web 应用启动脚本（Windows）
rem 双击此文件即可启动，然后浏览器打开 http://127.0.0.1:5000
cd /d "%~dp0"
echo ============================================
echo   后羿 HOUYI - 抗菌 Binder 设计平台
echo ============================================
echo.
echo 启动中，请稍候...
start "" http://127.0.0.1:5000
python webapp.py --port 5000
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0backend"
title Backend 8000
"D:\Program\python\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause

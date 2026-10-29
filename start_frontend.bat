@echo off
chcp 65001 >nul
cd /d "%~dp0frontend"
title Frontend 5173
call npm.cmd run dev
pause

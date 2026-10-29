@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Ollama Serve
"C:\Users\X\AppData\Local\Programs\Ollama\ollama.exe" serve
pause

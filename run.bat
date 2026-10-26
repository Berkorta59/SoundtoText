@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Once install.bat dosyasini calistirin.
  exit /b 1
)
.venv\Scripts\python.exe main.py

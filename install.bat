@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  where uv >nul 2>nul
  if not errorlevel 1 (
    uv venv --python 3.12 .venv
  ) else (
    where py >nul 2>nul
    if not errorlevel 1 (
      py -3.12 -m venv .venv
      if errorlevel 1 py -3 -m venv .venv
    ) else (
      echo Python 3.12 veya uv bulunamadi. Python 3.10-3.14 kurun.
      exit /b 1
    )
  )
)
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
echo Kurulum tamamlandi. run.bat ile uygulamayi baslatin.
echo Ilk model indirmesi icin internet baglantisi gerekir.

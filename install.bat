@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  where uv >nul 2>nul
  if not errorlevel 1 (
    uv venv --python 3.12 .venv
    if errorlevel 1 (
      echo uv ile Python 3.12 kurulumu basarisiz oldu.
      exit /b 1
    )
  ) else (
    py -3.12 -c "import sys" >nul 2>nul
    if errorlevel 1 (
      echo Python 3.12 bulunamadi. winget ile kuruluyor...
      where winget >nul 2>nul
      if errorlevel 1 (
        echo Python veya winget bulunamadi.
        echo Python 3.10-3.14'u manuel olarak kurup tekrar deneyin.
        exit /b 1
      )
      winget install --id Python.Python.3.12 --exact --scope user --accept-source-agreements --accept-package-agreements
      if errorlevel 1 (
        echo Python kurulumu basarisiz oldu.
        exit /b 1
      )
    )
    py -3.12 -m venv .venv
    if errorlevel 1 (
      echo Python 3.12 ile sanal ortam olusturulamadi.
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

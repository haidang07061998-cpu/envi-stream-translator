@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Dich EN-VI tren localhost + GPU Kaggle
cd /d "%~dp0"

echo ============================================================
echo   DICH EN-VI TREN LOCALHOST  +  GPU KAGGLE
echo ============================================================
echo.
echo   CACH DUNG:
echo     1. Tren Kaggle: bam "Run" cell 2, doi script in ra URL
echo     2. Bam "Copy" o goc cell  -  hoac boi den dong URL roi Ctrl+C
echo     3. Nhay dup file nay  -  no TU DOC clipboard, TU LUU, TU KIEM TRA
echo.
echo   Khong co URL trong clipboard cung khong sao: se dich tai may CPU.
echo ============================================================
echo.

REM ============================================================
REM 1) Neu server da chay san thi chi mo trang, khong mo them
REM ============================================================
powershell -NoProfile -Command "try{$r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 3; exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel! equ 0 (
  echo [i] Server da chay san tren cong 8000 - chi mo trang.
  goto :open
)

REM ============================================================
REM 2) Lay URL may GPU tu clipboard  -  khong can go tay
REM ============================================================
echo [1/3] Doc URL tu clipboard...
python scripts\set_gpu_url.py
set RC=!errorlevel!
if !RC! equ 0 echo       ^-^> Da luu URL, may GPU dang hoat dong.
if !RC! equ 2 echo       ^-^> Da luu URL nhung CHUA ket noi duoc. Van chay tiep o che do CPU.
if !RC! equ 1 (
  echo       Khong thay URL trong clipboard.
  echo.
  echo       Dan URL vao day roi bam Enter  ^(bo trong = dich tai may CPU^):
  set /p MANUALURL=
  if not "!MANUALURL!"=="" (
    python scripts\set_gpu_url.py --text "!MANUALURL!"
  ) else (
    echo       ^-^> Bo qua. Se dich ngay tai may ^(CPU^).
  )
)
echo.

REM ============================================================
REM 3) Lay IP trong LAN de ma QR / link nguoi nghe dung duoc tren dien thoai
REM ============================================================
set LANIP=127.0.0.1
for /f "delims=" %%i in ('python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0])" 2^>nul') do set LANIP=%%i
echo [2/3] Dia chi trong mang LAN: !LANIP!
echo.

REM ============================================================
REM 4) Chay server o cua so rieng
REM    LUU Y: KHONG dat CONFIDENTIAL=1  (che do hop mat se CHAN gui text len GPU)
REM ============================================================
echo [3/3] Khoi dong server...
start "EN-VI Server  (dong cua so nay de tat)" cmd /k "set OFFLINE=0&& set ASR_MODEL_OFFLINE=tiny.en&& set PARTIAL_EVERY=0.8&& set SERVER_HOST=http://!LANIP!:8000&& python -m uvicorn app.server:app --host 0.0.0.0 --port 8000"

echo       Dang tai model ASR, doi khoang 10-30 giay...
set /a TRIES=0
:waitready
ping -n 3 127.0.0.1 >nul
powershell -NoProfile -Command "try{$r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 3; exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel! neq 0 (
  set /a TRIES+=1
  if !TRIES! lss 30 goto :waitready
  echo       [!] Server chua len sau 60 giay. Xem cua so "EN-VI Server" de biet loi.
  goto :open
)
echo       Server da san sang.

:open
echo.
echo ============================================================
echo   DANG MO TRANG LOCALHOST
echo ============================================================
echo.
echo   Noi tieng Anh      : http://localhost:8000/m
echo   Do tre thuc te     : http://localhost:8000/metrics
echo   Kiem tra GPU/CPU   : http://localhost:8000/health
echo.
echo   Nguoi nghe tren dien thoai cung WiFi:
echo      mo http://!LANIP!:8000/m  roi bam BAT MIC  ^-^>  hien link + ma QR
echo      ^(dien thoai chi NGHE duoc; mic tren dien thoai can https^)
echo.
echo   Tat server: dong cua so "EN-VI Server"
echo ============================================================
start "" http://localhost:8000/m
echo.
pause
endlocal

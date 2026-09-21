@echo off
REM KHONG dat "chcp 65001" o day: cmd se khong doc duoc input cua "set /p" khi
REM stdin la file/pipe (loi da gap that: menu khong nhan duoc lua chon).
REM Toan bo chu trong file nay la ASCII nen khong can UTF-8.
setlocal enabledelayedexpansion
title DICH EN-VI - chon che do
cd /d "%~dp0"

REM ============================================================================
REM  MOT FILE DUY NHAT
REM
REM  Mo file -> chon che do:
REM    [1] OFFLINE : dich bang CPU tai may, KHONG gui gi ra Internet
REM                  -> chay thang, mo localhost
REM    [2] ONLINE  : dich bang GPU Kaggle (nhanh ~20x)
REM                  -> PHAI nhap URL Kaggle, kiem tra xong moi mo localhost
REM    [3] App desktop (khong can trinh duyet)
REM ============================================================================

:menu
cls
echo ============================================================
echo   DICH EN-VI  -  CHON CHE DO
echo ============================================================
echo.
echo   [1] OFFLINE  - dich tai may ^(CPU^), KHONG gui gi ra Internet
echo   [2] ONLINE   - dich bang GPU Kaggle, nhanh ~20x  ^(can URL^)
echo   [3] App desktop - khong can trinh duyet / localhost
echo   [0] Thoat
echo.
set "CH="
set /p "CH=  Chon 1-3  (Enter = 1): "
if "!CH!"=="" set "CH=1"
if "!CH!"=="0" goto :end
if "!CH!"=="1" goto :offline
if "!CH!"=="2" goto :online
if "!CH!"=="3" goto :desktop
goto :menu

REM ============================================================
REM  [1] OFFLINE -> localhost luon
REM ============================================================
:offline
echo.
echo   CHE DO OFFLINE: dich bang CPU tai may, khong gui gi ra Internet.
python scripts\set_gpu_url.py --clear >nul 2>&1
set "ENV_OFFLINE=1"
set "ENV_CONF=1"
goto :startserver

REM ============================================================
REM  [2] ONLINE -> phai nhap URL Kaggle truoc
REM ============================================================
:online
echo.
echo ------------------------------------------------------------
echo   CHE DO ONLINE - dich bang GPU Kaggle
echo ------------------------------------------------------------
echo   Lay URL o dau: mo notebook Kaggle -^> bam "Run" cell 2
echo                  -^> doi script in ra URL -^> bam "Copy" o goc cell
echo.

:askurl
set "U="
set /p "U=  Dan URL vao day roi Enter (bo trong = quay lai menu): "
if "!U!"=="" goto :menu
echo   Dang kiem tra may GPU...
python scripts\set_gpu_url.py --text "!U!"
if !errorlevel! neq 0 (
  echo.
  echo   [!] URL chua dung hoac may GPU chua san sang.
  echo       Kiem tra: cell Kaggle con chay? Da bat Internet cho notebook?
  echo.
  goto :askurl
)
echo.
echo   [OK] May GPU da san sang.
set "ENV_OFFLINE=0"
set "ENV_CONF="
goto :startserver

REM ============================================================
REM  [3] APP DESKTOP
REM ============================================================
:desktop
echo.
echo   APP DESKTOP: tu quyet theo gpu_url.txt
echo     - co URL Kaggle  -^> dung GPU tu xa
echo     - khong co       -^> hop mat offline ^(CPU^)
echo.
set "OFFLINE=1"
set "ASR_MODEL_OFFLINE=tiny.en"
set "PARTIAL_EVERY=0.8"
python desktop_app_v2.py
goto :end

REM ============================================================
REM  KHOI DONG SERVER + MO LOCALHOST
REM ============================================================
:startserver

REM --- TAT SERVER CU (tim theo cong 8000 - dang tin hon file PID) ---
REM     Dung Stop-Process (khong dung taskkill: taskkill co the bi chan quyen)
echo   Kiem tra server cu...
powershell -NoProfile -Command "$p=@(); netstat -ano | Select-String 'LISTENING' | Select-String ':8000' | ForEach-Object { $t=($_ -split '\s+')[-1]; if($t -match '^\d+$'){ $p += [int]$t } }; $p | Sort-Object -Unique | ForEach-Object { Write-Host ('   dung server cu PID ' + $_); Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
del server.pid >nul 2>&1
ping -n 3 127.0.0.1 >nul

REM --- IP trong LAN de ma QR / link nguoi nghe dung duoc tren dien thoai ---
set "LANIP=127.0.0.1"
for /f "delims=" %%i in ('python -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0])" 2^>nul') do set "LANIP=%%i"

echo.
echo   Khoi dong server  ^(che do: !ENV_OFFLINE! ^| LAN IP !LANIP!^)...
start "EN-VI Server  (dong cua so nay de tat)" cmd /k "set OFFLINE=!ENV_OFFLINE!&& set CONFIDENTIAL=!ENV_CONF!&& set ASR_MODEL_OFFLINE=tiny.en&& set PARTIAL_EVERY=0.8&& set SERVER_HOST=http://!LANIP!:8000&& python -m uvicorn app.server:app --host 0.0.0.0 --port 8000"

echo   Dang tai model ASR, doi 10-30 giay...
set /a TRIES=0
:waitready
ping -n 3 127.0.0.1 >nul
powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 3 | Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel! neq 0 (
  set /a TRIES+=1
  if !TRIES! lss 30 goto :waitready
  echo   [!] Server chua len sau 60 giay - xem cua so "EN-VI Server".
  goto :afterready
)
echo   Server san sang.

:afterready
REM --- hien ro dang o che do nao ---
set "MODE_TXT=OFFLINE (CPU tai may)"
set "MODE_NOTE=Khong gui gi ra Internet."
if "!ENV_OFFLINE!"=="0" (
  set "MODE_TXT=ONLINE (GPU Kaggle)"
  set "MODE_NOTE=Chi gui TEXT len GPU, audio khong roi khoi may."
)
echo.
echo ============================================================
echo   MO TRANG LOCALHOST      CHE DO: !MODE_TXT!
echo ============================================================
echo   !MODE_NOTE!
echo.
echo   Noi tieng Anh    : http://localhost:8000/m
echo   Do tre thuc te   : http://localhost:8000/metrics
echo   Dang dung GPU?   : http://localhost:8000/health
echo.
echo   Nguoi nghe tren dien thoai cung WiFi:
echo      mo http://!LANIP!:8000/m  -^> bam BAT MIC -^> hien link + ma QR
echo      ^(dien thoai chi NGHE duoc; mic tren dien thoai can https^)
echo.
echo   Tat server : dong cua so "EN-VI Server"
echo   Doi che do : chay lai file nay va chon lai
echo ============================================================
start "" http://localhost:8000/m
echo.
pause
goto :end

:end
endlocal

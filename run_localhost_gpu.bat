@echo off
REM ============================================================================
REM  SERVER LOCAL (localhost:8000) + DICH BANG GPU KAGGLE/COLAB
REM
REM  - ASR + PWA + phong + QR  : chay TAI MAY BAN (localhost:8000)
REM  - Dich EN -> VI           : gui TEXT len may GPU (khong gui audio)
REM
REM  Can: file gpu_url.txt chua dia chi may GPU (dan URL tu Kaggle/Colab).
REM        Chua co -> se dich ngay tai may (CPU, cham hon).
REM
REM  Sau khi chay:
REM    - May nay        : http://localhost:8000/m          (noi tieng Anh)
REM    - Nguoi nghe     : http://localhost:8000/room/<sid> (hoac quet QR)
REM    - Dien thoai cung WiFi: http://<IP-LAN>:8000/room/<sid>  (chi de NGHE,
REM      vi mic tren trinh duyet can localhost hoac https)
REM    - Do tre         : http://localhost:8000/metrics
REM
REM  KHONG dat CONFIDENTIAL=1 o day: che do hop mat se CHAN gui text len GPU.
REM  Muon hop mat nghiem ngat thi dung run_hop_mat_offline.bat
REM ============================================================================
set OFFLINE=0
set ASR_MODEL_OFFLINE=tiny.en
set PARTIAL_EVERY=0.8
echo ============================================================
echo  Server local: http://localhost:8000
if exist gpu_url.txt (
  echo  Dich EN-^>VI bang GPU: xem gpu_url.txt
) else (
  echo  CHUA co gpu_url.txt -^> dich ngay tai may ^(CPU, cham hon^)
  echo  Lay URL tu Kaggle/Colab roi luu vao gpu_url.txt
)
echo ============================================================
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
pause

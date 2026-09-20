@echo off
REM App desktop v2 - khong localhost, khong browser. Double-click chay.
REM KHONG ep ASR_MODEL (ep se khien may co GPU van chay model nho nhat).
REM ASR_MODEL_OFFLINE chi dung khi may KHONG co GPU (CPU) -> nhe, nhanh.
REM
REM CHE DO TU DONG:
REM   - Co gpu_url.txt (may GPU thue)  -> HYBRID: chi TEXT gui len GPU
REM   - Khong co gpu_url.txt           -> HOP MAT: 100% tai may, khong ra Internet
REM Muon ep che do hop mat du moi truong hop: dung run_desktop_offline.bat
set OFFLINE=1
set ASR_MODEL_OFFLINE=tiny.en
set PARTIAL_EVERY=0.8
python desktop_app_v2.py
pause

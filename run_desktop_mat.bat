@echo off
REM App desktop MAT - khong localhost, khong browser. Double-click chay.
set OFFLINE=1
set CONFIDENTIAL=1
set ASR_MODEL=tiny.en
set PARTIAL_EVERY=0.8
python desktop_app.py
pause

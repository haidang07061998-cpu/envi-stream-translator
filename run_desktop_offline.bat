@echo off
REM App desktop v2 o che do HOP MAT NGHIEM NGAT: khong gui gi ra Internet.
REM Dung khi hop noi bo / du lieu nhay cam: se KHONG dung may GPU thue du da cau hinh.
REM Doi lai: NMT chay tai may nen CHAM hon (CPU).
set OFFLINE=1
set CONFIDENTIAL=1
set ASR_MODEL_OFFLINE=tiny.en
set PARTIAL_EVERY=0.8
python desktop_app_v2.py
pause

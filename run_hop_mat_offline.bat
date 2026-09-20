@echo off
REM May hop MAT - offline 100%%, sub nhanh, tu xoa sau xuat file.
REM Luong: mic EN -> sub EN man hinh 1 -> dich VI man hinh 2 -> xuat TXT.
set OFFLINE=1
set CONFIDENTIAL=1
set ASR_MODEL=tiny.en
set PARTIAL_EVERY=0.8
REM Khong dung Redis (RAM only, tu xoa khi tat may)
set REDIS_URL=
echo Dang khoi dong che do HOP MAT OFFLINE (tiny.en, sub ~1s)...
python -m uvicorn app.server:app --host 127.0.0.1 --port 8000 --workers 1
pause

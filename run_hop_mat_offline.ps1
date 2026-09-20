# May hop MAT - offline 100%, sub nhanh, tu xoa sau xuat file.
# Luong: mic EN -> sub EN man hinh 1 -> dich VI man hinh 2 -> xuat TXT.
$env:OFFLINE='1'
$env:CONFIDENTIAL='1'
$env:ASR_MODEL='tiny.en'
$env:PARTIAL_EVERY='0.8'
$env:REDIS_URL=''
Write-Host "Dang khoi dong che do HOP MAT OFFLINE (tiny.en, sub ~1s)..." -ForegroundColor Green
python -m uvicorn app.server:app --host 127.0.0.1 --port 8000 --workers 1

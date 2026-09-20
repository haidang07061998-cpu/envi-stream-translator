"""Tai san tat ca model de chay OFFLINE 100% (chi can mang 1 lan).
Chay: python scripts/download_offline_models.py
Xong: OFFLINE=1 python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
Luong offline: mic EN -> sub EN man hinh 1 -> dich VI man hinh 2 -> doc VI offline + xuat txt.
"""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(BASE, "models")
PIPER_DIR = os.path.join(MODELS, "piper")
os.makedirs(PIPER_DIR, exist_ok=True)

print("== 1/3 Tai ASR faster-whisper (tiny.en + large-v3-turbo) ==")
try:
    from faster_whisper import WhisperModel
    for m in ["tiny.en", "large-v3-turbo"]:
        print(f" -> {m} ...")
        WhisperModel(m, device="cpu", compute_type="int8")
    print("ASR OK (cache trong ~/.cache/huggingface)")
except Exception as e:
    print("ASR loi:", e)

print("== 2/3 Tai NMT VinAI en2vi-v2 ==")
try:
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    mid = "vinai/vinai-translate-en2vi-v2"
    AutoTokenizer.from_pretrained(mid, src_lang="en_XX")
    AutoModelForSeq2SeqLM.from_pretrained(mid)
    print("NMT OK")
except Exception as e:
    print("NMT loi:", e)

print("== 3/3 Tai giong Piper vi_VN offline ==")
# Model nhe, giay phep MIT, chay hoan toan offline
URLS = [
    ("https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx",
     os.path.join(PIPER_DIR, "vi_VN-vais1000-medium.onnx")),
    ("https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json",
     os.path.join(PIPER_DIR, "vi_VN-vais1000-medium.onnx.json")),
]
try:
    import urllib.request
    for url, out in URLS:
        if os.path.exists(out):
            print(f" da co {out}")
            continue
        print(f" -> tai {os.path.basename(out)} ...")
        urllib.request.urlretrieve(url, out)
    print("Piper OK")
except Exception as e:
    print("Piper loi (van chay duoc bang SAPI5 Windows):", e)

print("\nXONG. Chay offline:")
print("  Windows CMD: set OFFLINE=1 && python -m uvicorn app.server:app --host 0.0.0.0 --port 8000")
print("  PowerShell: $env:OFFLINE='1'; python -m uvicorn app.server:app --host 0.0.0.0 --port 8000")

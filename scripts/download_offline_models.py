"""Tai san TAT CA model de chay OFFLINE 100% (chi can mang 1 lan).

Chay: python scripts/download_offline_models.py

Tai het vao thu muc `models/` cua repo (khong phai cache HuggingFace), de sau khi
copy thu muc nay sang may hop mat la chay duoc ngay, khong can mang.
`src/config.py:local_model_dir()` + `asr.py` + `nmt.py` se tu uu tien ban trong models/.

Sau khi xong:
    set OFFLINE=1 & set CONFIDENTIAL=1
    python -m uvicorn app.server:app --host 127.0.0.1 --port 8000
"""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(BASE, "models")
PIPER_DIR = os.path.join(MODELS, "piper")
os.makedirs(PIPER_DIR, exist_ok=True)

ASR_NAMES = ["tiny.en", "large-v3-turbo"]
NMT_REPO = "vinai/vinai-translate-en2vi-v2"


def download_hf(repo_id, local_dir, label):
    try:
        from huggingface_hub import snapshot_download
    except Exception as e:
        print(f"  [!] thieu huggingface_hub ({e}) -> bo qua {label}")
        return False
    try:
        os.makedirs(local_dir, exist_ok=True)
        snapshot_download(repo_id=repo_id, local_dir=local_dir,
                          local_dir_use_symlinks=False,
                          ignore_patterns=["*.msgpack", "*.h5", "*.ot", "*.safetensors"])
        print(f"  [x] {label} -> {local_dir}")
        return True
    except Exception as e:
        print(f"  [!] {label} loi: {type(e).__name__}: {e}")
        return False


print("== 1/3 ASR faster-whisper (tiny.en + large-v3-turbo) ==")
try:
    from faster_whisper.utils import _MODELS as FW_MODELS
except Exception:
    FW_MODELS = {}
for name in ASR_NAMES:
    repo = FW_MODELS.get(name) or f"Systran/faster-whisper-{name}"
    out = os.path.join(MODELS, f"faster-whisper-{name}")
    if os.path.isdir(out) and os.listdir(out):
        print(f"  da co {out}")
        continue
    download_hf(repo, out, f"ASR {name} ({repo})")

print("== 2/3 NMT VinAI en2vi-v2 ==")
nmt_out = os.path.join(MODELS, "vinai-translate-en2vi-v2")
if os.path.isdir(nmt_out) and os.listdir(nmt_out):
    print(f"  da co {nmt_out}")
else:
    download_hf(NMT_REPO, nmt_out, "NMT VinAI en2vi-v2")

print("== 3/3 Giong Piper vi_VN offline (nhe, MIT) ==")
URLS = [
    ("https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/"
     "vi_VN-vais1000-medium.onnx",
     os.path.join(PIPER_DIR, "vi_VN-vais1000-medium.onnx")),
    ("https://huggingface.co/rhasspy/piper-voices/resolve/main/vi/vi_VN/vais1000/medium/"
     "vi_VN-vais1000-medium.onnx.json",
     os.path.join(PIPER_DIR, "vi_VN-vais1000-medium.onnx.json")),
]
try:
    import urllib.request
    for url, out in URLS:
        if os.path.exists(out):
            print(f"  da co {out}")
            continue
        print(f"  -> tai {os.path.basename(out)} ...")
        urllib.request.urlretrieve(url, out)
    print("  [x] Piper OK")
except Exception as e:
    print(f"  [!] Piper loi (van chay duoc bang SAPI5 Windows): {e}")

print("\nKIEM TRA: python -c \"from src.config import DEFAULT, local_model_dir;"
      "print('ASR:', DEFAULT.resolve_asr_model(False));"
      "print('NMT:', DEFAULT.resolve_nmt_path())\"")
print("XONG. Chay offline:")
print("  Windows CMD : set OFFLINE=1 && set CONFIDENTIAL=1 && "
      "python -m uvicorn app.server:app --host 127.0.0.1 --port 8000")
print("  PowerShell  : $env:OFFLINE='1'; $env:CONFIDENTIAL='1'; "
      "python -m uvicorn app.server:app --host 127.0.0.1 --port 8000")

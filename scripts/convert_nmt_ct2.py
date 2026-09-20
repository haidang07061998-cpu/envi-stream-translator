"""Convert VinAI en2vi-v2 sang CTranslate2 int8 (nhanh 4-5x, RAM /4, giữ ~99% BLEU).
Chạy 1 lần có mạng: python scripts/convert_nmt_ct2.py
Sau đó desktop_app_v2 tự dùng models/ct2-en2vi-v2-int8, không cần mạng nữa.
Nguồn: Agent 2 (CTranslate2 mBART, beam=1 skip softmax, int8_float32).
"""
import os
import subprocess
import sys

MODEL = os.getenv("NMT_MODEL", "vinai/vinai-translate-en2vi-v2")
OUT = os.getenv("CT2_OUT", "models/ct2-en2vi-v2-int8")

os.makedirs("models", exist_ok=True)
cmd = [
    sys.executable, "-m", "pip", "install", "-q",
    "ctranslate2", "transformers", "sentencepiece",
]
print("Cài CT2 tools...")
subprocess.run(cmd, check=False)

conv = [
    "ct2-transformers-converter",
    "--model", MODEL,
    "--output_dir", OUT,
    "--quantization", "int8_float32",
    "--copy_files", "tokenizer.json", "tokenizer_config.json",
]
print("Convert:", " ".join(conv))
r = subprocess.run(conv)
if r.returncode == 0:
    print(f"XONG. Model CT2 tại {OUT}. Desktop v2 sẽ tự dùng (set CT2_EN2VI={OUT} nếu cần).")
else:
    print("Convert thất bại. Kiểm tra mạng + dung lượng. App vẫn chạy HF PyTorch fallback.")

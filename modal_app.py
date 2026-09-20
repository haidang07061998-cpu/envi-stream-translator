"""Chay server dich EN->VI tren GPU MIEN PHI cua Modal (co URL public).

Modal tang $30 compute mien phi moi thang o goi Starter (~50 gio GPU T4) va co
chuong trinh tai tro sinh vien/nghien cuu sinh toi $10.000:
    https://modal.com/pricing  ->  "Credit grants for academics"

--------------------------------------------------------------------------------
CACH DUNG (1 lan):
    pip install modal
    modal token new                 # dang nhap (mo trinh duyet)
    modal deploy modal_app.py       # ~5 phut lan dau (build image + tai model)
Modal se in ra mot URL dang:  https://<ten>--envi-translator-fastapi-app.modal.run
--------------------------------------------------------------------------------

Sau do tren MAY BAN khong can model nang:
  * Cach 1 - dung truc tiep: mo <URL>/m de noi, <URL>/room/<sid> cho nguoi nghe.
    (URL la https:// nen MIC CHAY DUOC tren ca dien thoai - tot hon localhost)
  * Cach 2 - HYBRID (khuyen nghi cho may yeu): giu ASR o may, chi gui TEXT len GPU:
        set NMT_REMOTE_URL=https://<URL>
        python desktop_app_v2.py          # hoac run_desktop_v2.bat
    => may ban chi ton ~300MB RAM thay vi ~2.2GB, va khong ton CPU de dich.

LUU Y: file nay CHUA duoc chay thu tren Modal that (khong co tai khoan trong moi
truong phat trien). Neu `modal deploy` bao loi, xem phan troubleshooting o cuoi file.
"""
import os

import modal

APP_NAME = "envi-translator"
REPO_DIR = "/root/envi"
MODELS_DIR = f"{REPO_DIR}/models"

# GPU: "T4" ($0.59/h - du dung) | "L4" ($0.80/h, nhanh hon) | "A10G" | "A100"
GPU = os.getenv("MODAL_GPU", "T4")
# Model ASR: GPU nen dung ban tot nhat
ASR_MODEL = os.getenv("MODAL_ASR_MODEL", "large-v3-turbo")

app = modal.App(APP_NAME)

# --- Image: copy code + cai dependencies ------------------------------------
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1", "git")
    .pip_install(
        "faster-whisper>=1.0.0",
        "transformers>=4.40.0",
        "sentencepiece>=0.2.0",
        "numpy>=1.26.0",
        "scipy>=1.11.0",
        "soundfile>=0.12.0",
        "fastapi",
        "uvicorn[standard]",
        "websockets",
        "python-multipart",
        "qrcode[pil]",
        "edge-tts>=2.0.0",
    )
    # torch ban CUDA: Modal co GPU nen phai la ban cu121, khong phai ban CPU
    .pip_install("torch>=2.2.0", extra_index_url="https://download.pytorch.org/whl/cu121")
    # copy toan bo repo (tru models/ - se nam trong Volume)
    .add_local_dir(
        ".",
        remote_path=REPO_DIR,
        ignore=["models", "out", ".git", "__pycache__", "*.log", ".playwright-mcp"],
    )
)

# --- Volume: cache model, chi tai 1 lan duy nhat ----------------------------
vol = modal.Volume.from_name("envi-models", create_if_missing=True)


@app.function(
    image=image,
    gpu=GPU,
    volumes={MODELS_DIR: vol},
    timeout=3600,
    scaledown_window=300,      # giu container 5 phut sau request cuoi -> demo lien mach
    max_containers=1,          # 1 container de khong nhan doi chi phi
)
@modal.concurrent(max_inputs=16)     # nhieu nguoi nghe cung luc
@modal.asgi_app()
def fastapi_app():
    """Tra ve ung dung FastAPI cua du an (app/server.py)."""
    import sys

    sys.path.insert(0, REPO_DIR)
    os.chdir(REPO_DIR)

    # lan dau: Volume rong -> tai model vao Volume (chi 1 lan, sau do dung lai)
    if not os.path.isdir(os.path.join(MODELS_DIR, "vinai-translate-en2vi-v2")):
        print("[modal] Volume rong -> tai model (lan dau, vai phut)...", flush=True)
        import subprocess
        subprocess.run([sys.executable, "scripts/download_offline_models.py"], check=False)
        try:
            vol.commit()
            print("[modal] da luu model vao Volume", flush=True)
        except Exception as e:
            print(f"[modal] khong commit duoc Volume: {e}", flush=True)

    os.environ.setdefault("ASR_MODEL", ASR_MODEL)
    os.environ.setdefault("MODE", "translate")
    # Ghi ro: GPU nen khong can CT2 (da do la sinh van ban lap vo nghia)
    os.environ.setdefault("DISABLE_CT2", "1")

    from app.server import app as fastapi
    return fastapi


@app.local_entrypoint()
def main():
    print(f"Deploy bang:  modal deploy {os.path.basename(__file__)}")
    print(f"GPU du kien:  {GPU}  |  ASR: {ASR_MODEL}")


# ---------------------------------------------------------------------------
# TROUBLESHOOTING
# 1) "modal: command not found"      -> pip install modal
# 2) Loi tai model (HF bi chan)      -> them HF_TOKEN qua: modal secret create hf HF_TOKEN=hf_xxx
#                                       roi them secrets=[modal.Secret.from_name("hf")] vao @app.function
# 3) Het $30 mien phi                -> xem muc "Credit grants for academics" (toi $10k cho sinh vien)
# 4) Muon dung GPU khac              -> set MODAL_GPU=L4 (hoac A10G/A100) truoc khi deploy
# 5) Container ngu sau 5 phut        -> tang scaledown_window (ton tien hon khi idle)
# 6) Do tre cao vi xa                -> Modal cho chon region: them region="ap-..." neu can

"""Chay server dich EN->VI tren GPU MIEN PHI cua Google Colab hoac Kaggle.

Ca hai deu cho GPU T4 mien phi (Kaggle: 30 gio/tuan; Colab: phien ngan hon).
Notebook khong mo duoc port ra Internet, nen script nay tu mo mot TUNNEL
(cloudflared) de ban co URL https://... truy cap tu may minh.

--------------------------------------------------------------------------------
CACH DUNG
  A) Google Colab:  Runtime -> Change runtime type -> T4 GPU
     Dan toan bo noi dung file nay vao 1 cell roi chay.
  B) Kaggle:        Settings -> Accelerator -> GPU T4 x2
     Dan vao 1 cell roi chay.

  Truoc khi chay, can dua CODE cua du an len notebook. Chon 1 trong 3:
    1. Upload file zip:  nen thu muc du an thanh envi-stream-translator.zip roi
       dung cell upload cua Colab (bieu tuong thu muc), hoac Kaggle > Add Data.
    2. Git:              sua GIT_URL ben duoi thanh repo cua ban.
    3. Da co san:        neu /content/envi-stream-translator (Colab) hoac
       /kaggle/working/envi-stream-translator (Kaggle) da ton tai thi dung luon.

  Script se in ra URL https://<ten>.trycloudflare.com
    - Mo <URL>/m            de NOI (mic chay duoc vi la https)
    - Mo <URL>/room/<sid>   cho nguoi nghe, hoac quet QR
    - Hoac tren may ban:  set NMT_REMOTE_URL=<URL>  -> chi gui TEXT len GPU
--------------------------------------------------------------------------------
"""
import os
import re
import subprocess
import sys
import threading
import time

# ============================ CAU HINH =====================================
GIT_URL = ""                       # vd "https://github.com/<ban>/envi-stream-translator.git"
ASR_MODEL = "large-v3-turbo"       # GPU nen dung ban tot nhat
PORT = 8000
MODE = "translate"                 # translate (EN->VI) | transcribe (chi EN)
# ===========================================================================

IS_COLAB = os.path.isdir("/content")
WORK = "/content" if IS_COLAB else "/kaggle/working"
CANDIDATES = [
    os.path.join(WORK, "envi-stream-translator"),
    "/content/envi-stream-translator",
    "/kaggle/working/envi-stream-translator",
]


def sh(cmd, check=False):
    print(f"$ {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip():
        print(r.stdout.strip()[-3000:], flush=True)
    if r.returncode != 0 and r.stderr.strip():
        print(f"[!] {r.stderr.strip()[-1500:]}", flush=True)
    if check and r.returncode != 0:
        raise SystemExit(f"lenh that bai: {cmd}")
    return r


def step1_deps():
    print("\n=== [1/4] Cai dat thu vien ===", flush=True)
    sh("pip install -q faster-whisper transformers sentencepiece "
       "fastapi 'uvicorn[standard]' websockets python-multipart "
       "qrcode[pil] edge-tts soundfile scipy", check=False)
    import torch
    print(f"torch {torch.__version__} | CUDA san sang: {torch.cuda.is_available()}", flush=True)
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)
    else:
        print("[!] KHONG thay GPU. Vao Runtime/Settings bat GPU T4 roi chay lai.", flush=True)


def step2_code():
    print("\n=== [2/4] Lay code du an ===", flush=True)
    for c in CANDIDATES:
        if os.path.isdir(c):
            print(f"da co: {c}", flush=True)
            return c
    if GIT_URL:
        sh(f"git clone --depth 1 {GIT_URL} {CANDIDATES[0]}", check=True)
        return CANDIDATES[0]
    # tim file zip da upload
    for d in (WORK, "/content", "/kaggle/input", "/content/drive/MyDrive"):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.lower().endswith(".zip") and "envi" in f.lower():
                z = os.path.join(d, f)
                print(f"thay zip: {z}", flush=True)
                sh(f"unzip -q -o '{z}' -d {WORK}")
                for c in CANDIDATES:
                    if os.path.isdir(c):
                        return c
    raise SystemExit(
        "KHONG tim thay code. Hay: (a) nen thu muc du an thanh "
        "envi-stream-translator.zip roi upload, hoac (b) dien GIT_URL o dau file.")


def step3_models(repo):
    print("\n=== [3/4] Tai model (1 lan, vai phut) ===", flush=True)
    os.chdir(repo)
    sys.path.insert(0, repo)
    sh(f"{sys.executable} scripts/download_offline_models.py", check=False)


def step4_serve(repo):
    print("\n=== [4/4] Chay server + mo tunnel ===", flush=True)
    os.chdir(repo)
    os.environ["ASR_MODEL"] = ASR_MODEL
    os.environ["MODE"] = MODE
    os.environ.setdefault("DISABLE_CT2", "1")   # da do: CT2 sinh van ban lap vo nghia

    def run_server():
        subprocess.run([sys.executable, "-m", "uvicorn", "app.server:app",
                        "--host", "0.0.0.0", "--port", str(PORT),
                        "--log-level", "warning"])

    threading.Thread(target=run_server, daemon=True).start()

    # cho server len
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=3)
            break
        except Exception:
            time.sleep(2)
    print("server da chay, dang tai model...", flush=True)

    # cloudflared: tao URL https mien phi, khong can tai khoan
    cf = os.path.join(WORK, "cloudflared")
    if not os.path.exists(cf):
        sh(f"wget -q -O {cf} https://github.com/cloudflare/cloudflared/releases/"
           f"latest/download/cloudflared-linux-amd64 && chmod +x {cf}", check=False)
    proc = subprocess.Popen([cf, "tunnel", "--url", f"http://localhost:{PORT}",
                             "--no-autoupdate"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    url = None
    t0 = time.time()
    while time.time() - t0 < 90:
        line = proc.stdout.readline()
        if not line:
            continue
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            url = m.group(0)
            break

    print("\n" + "=" * 66, flush=True)
    if url:
        print(f"  URL CUA BAN:  {url}", flush=True)
        print(f"    - Noi tieng Anh  : {url}/m", flush=True)
        print(f"    - Nguoi nghe     : {url}/room/<sid>  (tao phong o trang /m)", flush=True)
        print(f"    - Do tre         : {url}/metrics", flush=True)
        print(f"    - Chi gui TEXT   : set NMT_REMOTE_URL={url}  (roi chay desktop_app_v2.py)",
              flush=True)
    else:
        print("  KHONG lay duoc URL cloudflared. Thu lai, hoac dung cach khac:", flush=True)
        print("  - Colab: dung `from google.colab.output import eval_js; "
              "print(eval_js('google.colab.kernel.proxyPort(8000)'))`", flush=True)
    print("=" * 66, flush=True)
    print("\nLuu y: giu cell nay DANG CHAY trong luc trinh dien. Phien Kaggle ~9-12h,", flush=True)
    print("Colab ngan hon - nen bat dau lai neu bi ngat.", flush=True)
    print("Nhan Ctrl+C (hoac Stop cell) de dung.\n", flush=True)

    # giu tien trinh song
    while True:
        time.sleep(30)
        if proc.poll() is not None:
            print("[!] tunnel da dung.", flush=True)
            break


if __name__ == "__main__":
    repo = step2_code()
    step1_deps()
    step3_models(repo)
    step4_serve(repo)

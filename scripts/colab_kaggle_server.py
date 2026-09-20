"""Chay server dich EN->VI tren GPU MIEN PHI cua Kaggle hoac Google Colab.

Kaggle: 30 gio GPU T4 mien phi moi tuan. Colab: phien ngan hon.
Notebook khong mo duoc port ra Internet, nen script tu mo TUNNEL (cloudflared) de ban
co URL https://... truy cap tu may minh.

================================================================================
CACH DUNG TREN KAGGLE (5 buoc)
================================================================================
 1. Kaggle -> Datasets -> New Dataset -> keo tha file
    `dist/envi-stream-translator-kaggle.zip` (194 KB) -> Create
 2. Mo notebook cua ban -> Settings (panel phai):
      - Accelerator : GPU T4 x2
      - Internet    : ON          <-- BAT BUOC (de pip + tai model + tunnel)
 3. Add Input -> chon dataset vua tao
 4. Dan noi dung file nay vao 1 cell roi chay (hoac chay:
      !python /kaggle/input/<ten-dataset>/envi-stream-translator/scripts/colab_kaggle_server.py )
 5. Script in ra URL https://<ten>.trycloudflare.com
      - <URL>/m           : NOI tieng Anh (mic chay duoc vi la https)
      - <URL>/room/<sid>  : nguoi nghe, hoac quet QR
      - <URL>/metrics     : do tre thuc te

 TREN MAY BAN (neu muon may nhe - chi gui TEXT len GPU):
      set NMT_REMOTE_URL=https://<url>
      python desktop_app_v2.py
================================================================================
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time

# ============================ CAU HINH =====================================
GIT_URL = ""                       # tuy chon: "https://github.com/<ban>/repo.git"
ASR_MODEL = "large-v3-turbo"       # GPU nen dung ban tot nhat
PORT = int(os.getenv("PORT", "8000"))
MODE = "translate"                 # translate (EN->VI) | transcribe (chi EN)
KEEP_RUNNING = True                # False = chay thu roi thoat
# ===========================================================================

IS_KAGGLE = os.path.isdir("/kaggle")
IS_COLAB = os.path.isdir("/content")
if IS_KAGGLE:
    WORK = "/kaggle/working"
    INPUTS = ["/kaggle/input"]
elif IS_COLAB:
    WORK = "/content"
    INPUTS = ["/content", "/content/drive/MyDrive"]
else:
    WORK = os.getcwd()
    INPUTS = [os.getcwd()]

REPO_NAME = "envi-stream-translator"
MARKER = os.path.join("app", "server.py")      # dau hieu nhan biet thu muc du an
WRITABLE_REPO = os.path.join(WORK, REPO_NAME)


def log(m):
    print(m, flush=True)


def sh(cmd, check=False, quiet=False):
    if not quiet:
        log(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout.strip() and not quiet:
        log(r.stdout.strip()[-2500:])
    if r.returncode != 0 and r.stderr.strip():
        log(f"[!] {r.stderr.strip()[-1500:]}")
    if check and r.returncode != 0:
        raise SystemExit(f"lenh that bai: {cmd}")
    return r


# ---------------------------------------------------------------- 1. kiem tra
def step_check():
    log("=== [1/5] Kiem tra moi truong ===")
    log(f"  nen tang: {'Kaggle' if IS_KAGGLE else ('Colab' if IS_COLAB else 'may cuc bo')}")
    try:
        import torch
        log(f"  torch {torch.__version__} | CUDA: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            log(f"  GPU: {torch.cuda.get_device_name(0)}")
        else:
            log("  [!!] KHONG thay GPU.")
            if IS_KAGGLE:
                log("       -> Settings (panel phai) -> Accelerator -> GPU T4 x2, roi Run All lai")
            else:
                log("       -> Runtime -> Change runtime type -> T4 GPU")
    except Exception as e:
        log(f"  chua co torch ({e}) - se cai o buoc sau")

    # Internet: bat buoc de pip + tai model + tunnel
    r = subprocess.run("curl -s -m 8 -o /dev/null -w '%{http_code}' https://pypi.org",
                       shell=True, capture_output=True, text=True)
    ok = r.stdout.strip() in ("200", "301", "302")
    log(f"  Internet: {'OK' if ok else 'KHONG CO'}")
    if not ok:
        log("  [!!] BAT BUOC bat Internet:")
        if IS_KAGGLE:
            log("       Settings (panel phai) -> Internet -> ON (can xac minh so dien thoai)")
        else:
            log("       Colab thuong da co Internet san")
        raise SystemExit("Hay bat Internet roi chay lai.")
    return ok


# ---------------------------------------------------------------- 2. cai dat
def step_deps():
    log("\n=== [2/5] Cai thu vien con thieu ===")
    need = []
    for mod, pkg in [("faster_whisper", "faster-whisper"), ("transformers", "transformers"),
                     ("fastapi", "fastapi"), ("uvicorn", "uvicorn[standard]"),
                     ("websockets", "websockets"), ("multipart", "python-multipart"),
                     ("soundfile", "soundfile"), ("edge_tts", "edge-tts")]:
        try:
            __import__(mod)
        except Exception:
            need.append(pkg)
    if need:
        log(f"  can cai: {' '.join(need)}")
        sh(f"pip install -q {' '.join(need)}", check=False)
    else:
        log("  da co du thu vien")
    try:
        import torch
        log(f"  torch {torch.__version__} | CUDA {torch.cuda.is_available()}")
    except Exception:
        sh("pip install -q torch", check=False)


# ---------------------------------------------------------------- 3. lay code
def _looks_like_repo(d):
    return os.path.isfile(os.path.join(d, MARKER))


def find_repo():
    log("\n=== [3/5] Tim code du an ===")
    # da co ban ghi duoc trong WORK
    if _looks_like_repo(WRITABLE_REPO):
        log(f"  da co: {WRITABLE_REPO}")
        return WRITABLE_REPO
    # tim trong cac thu muc input (Kaggle dataset mount = CHI DOC)
    found = None
    for base in INPUTS:
        if not os.path.isdir(base):
            continue
        for root, dirs, _files in os.walk(base):
            depth = root[len(base):].count(os.sep)
            if depth > 4:
                dirs[:] = []
                continue
            if _looks_like_repo(root):
                found = root
                break
        if found:
            break
    if found:
        log(f"  thay trong input (chi doc): {found}")
        log(f"  -> copy sang {WRITABLE_REPO} (vi can ghi model vao day)")
        if os.path.isdir(WRITABLE_REPO):
            shutil.rmtree(WRITABLE_REPO, ignore_errors=True)
        shutil.copytree(found, WRITABLE_REPO)
        return WRITABLE_REPO
    # git clone
    if GIT_URL:
        sh(f"git clone --depth 1 {GIT_URL} {WRITABLE_REPO}", check=True)
        return WRITABLE_REPO
    # zip da upload
    for base in INPUTS + [WORK]:
        if not os.path.isdir(base):
            continue
        for f in os.listdir(base):
            if f.lower().endswith(".zip") and "envi" in f.lower():
                z = os.path.join(base, f)
                log(f"  thay zip: {z} -> giai nen")
                sh(f"unzip -q -o '{z}' -d {WORK}")
                for cand in (WRITABLE_REPO, os.path.join(WORK, REPO_NAME)):
                    if _looks_like_repo(cand):
                        return cand
    raise SystemExit(
        "KHONG tim thay code.\n"
        "  Cach nhanh nhat: Kaggle -> Datasets -> New Dataset -> upload file\n"
        "  'dist/envi-stream-translator-kaggle.zip' -> roi Add Input vao notebook nay.")


# ---------------------------------------------------------------- 4. model
def step_models(repo):
    log("\n=== [4/5] Tai model (lan dau vai phut) ===")
    os.chdir(repo)
    sys.path.insert(0, repo)
    if os.path.isdir(os.path.join(repo, "models", "vinai-translate-en2vi-v2")):
        log("  da co model trong models/")
        return
    sh(f"{sys.executable} scripts/download_offline_models.py", check=False)


# ---------------------------------------------------------------- 5. serve
def step_serve(repo):
    log("\n=== [5/5] Chay server + mo tunnel ===")
    os.chdir(repo)
    sys.path.insert(0, repo)
    os.environ["ASR_MODEL"] = ASR_MODEL
    os.environ["MODE"] = MODE
    os.environ.setdefault("DISABLE_CT2", "1")   # da do: CT2 sinh van ban lap vo nghia
    os.environ.setdefault("SERVER_HOST", "http://localhost")

    def run_server():
        subprocess.run([sys.executable, "-m", "uvicorn", "app.server:app",
                        "--host", "0.0.0.0", "--port", str(PORT),
                        "--log-level", "warning"])

    threading.Thread(target=run_server, daemon=True).start()

    import urllib.request
    up = False
    for _ in range(90):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=3)
            up = True
            break
        except Exception:
            time.sleep(2)
    log(f"  server: {'da len' if up else 'CHUA len (xem log phia tren)'}")
    log("  dang tai model vao GPU (1-3 phut lan dau)...")

    cf = os.path.join(WORK, "cloudflared")
    if not os.path.exists(cf):
        log("  tai cloudflared...")
        sh(f"wget -q -O {cf} https://github.com/cloudflare/cloudflared/releases/"
           f"latest/download/cloudflared-linux-amd64 && chmod +x {cf}", check=False)
    if not os.path.exists(cf):
        log("  [!] khong tai duoc cloudflared. Thu: pip install pycloudflared")
        return None

    proc = subprocess.Popen([cf, "tunnel", "--url", f"http://localhost:{PORT}",
                             "--no-autoupdate"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url, t0 = None, time.time()
    while time.time() - t0 < 120:
        line = proc.stdout.readline()
        if not line:
            continue
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            url = m.group(0)
            break

    log("\n" + "=" * 70)
    if url:
        log(f"  URL CUA BAN:  {url}")
        log(f"    Noi tieng Anh   : {url}/m")
        log(f"    Nguoi nghe      : {url}/room/<sid>   (tao phong o trang /m)")
        log(f"    Do tre          : {url}/metrics")
        log(f"    Chi gui TEXT    : set NMT_REMOTE_URL={url}")
        log(f"                      (roi chay desktop_app_v2.py tren may ban)")
    else:
        log("  KHONG lay duoc URL cloudflared. Thu lai, hoac xem log tunnel phia tren.")
    log("=" * 70)
    log("\nGIU CELL NAY DANG CHAY trong luc trinh dien (Kaggle ~9-12h/ phien).")
    log("Bam Stop de dung.\n")

    if not KEEP_RUNNING:
        return url
    while True:
        time.sleep(30)
        if proc.poll() is not None:
            log("[!] tunnel da dung.")
            break
    return url


def main():
    log("=" * 70)
    log("  DICH EN->VI TREN GPU MIEN PHI (Kaggle / Colab)")
    log("=" * 70)
    step_check()
    step_deps()
    repo = find_repo()
    step_models(repo)
    step_serve(repo)


if __name__ == "__main__":
    main()

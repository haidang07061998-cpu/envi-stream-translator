"""Cau hinh TAP TRUNG cho toan he thong (chi 1 cap ngon ngu: EN -> VI).

Day la NGUON DUY NHAT cho moi tham so. Server, desktop, gradio deu doc tu day,
khong hardcode so o trong app nua. Moi tham so deu ghi de duoc bang bien moi truong.

Vi du:
    set OFFLINE=1 & set CONFIDENTIAL=1 & set ASR_MODEL=tiny.en
    set PARTIAL_EVERY=0.6 & set FINAL_SILENCE=0.6 & set MODE=translate
"""
from dataclasses import dataclass
import os
import re

# Thu muc goc repo (src/..) - de tim ban model da tai san trong models/
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def local_model_dir(name: str):
    """Tim ban model da tai san trong models/ (chay offline that su, khong can cache HF).

    Chap nhan:
      - duong dan that            -> dung neu ton tai
      - ID HuggingFace "org/ten"  -> tim models/<ten>
      - ten ngan "tiny.en"        -> tim models/<ten> hoac models/faster-whisper-<ten>
    Tra ve duong dan tuyet doi neu co, nguoc lai None.
    """
    if not name:
        return None
    if os.path.isdir(name):
        return name
    if os.sep in name and os.path.isabs(name):
        return None                       # duong dan tuyet doi nhung khong ton tai
    base = name.replace("\\", "/").split("/")[-1]
    if not base:
        return None
    cands = [
        os.path.join(_BASE, "models", base),
        os.path.join(_BASE, "models", f"faster-whisper-{base}"),
        os.path.join(_BASE, "models", base.replace(".", "-")),
    ]
    for c in cands:
        try:
            if not (os.path.isdir(c) and os.listdir(c)):
                continue
        except OSError:
            continue
        # QUAN TRONG: sentencepiece (C++) tren Windows KHONG doc duoc duong dan chua
        # ky tu ngoai ASCII (vd "F:\\5 bai test\\..."). Neu tra ve duong dan tuyet doi
        # kieu do thi tokenizer se bao "Unable to load vocabulary from file".
        # -> uu tien duong dan TUONG DOI (thuong la ASCII), neu khong duoc thi tra None
        #    de caller dung ban HuggingFace (cache nam o C:\Users\... la ASCII).
        if _ascii_ok(c):
            return c
        try:
            rel = os.path.relpath(c, os.getcwd())
        except Exception:
            rel = None
        if rel and not os.path.isabs(rel) and _ascii_ok(rel):
            return rel
        print(f"[config] CANH BAO: '{c}' chua ky tu ngoai ASCII nen sentencepiece "
              f"khong doc duoc -> dung ban HuggingFace. Nen chuyen repo sang thu muc "
              f"khong dau (vd F:\\projects\\envi-stream-translator).")
        return None
    return None


def _ascii_ok(path: str) -> bool:
    try:
        path.encode("ascii")
        return True
    except (UnicodeEncodeError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Dia chi may GPU thue (Kaggle / Colab / Modal)
# ---------------------------------------------------------------------------
GPU_URL_FILE = "gpu_url.txt"       # dat o thu muc goc repo, ghi 1 dong URL
GPU_URL_ENV = "NMT_REMOTE_URL"


def resolve_nmt_remote() -> str:
    """Tim dia chi may GPU, theo thu tu uu tien:

    1. Bien moi truong NMT_REMOTE_URL   (dat tam cho 1 phien)
    2. File `gpu_url.txt` o goc repo    (nho san giua cac lan chay)
    3. File `.env` voi dong NMT_REMOTE_URL=...

    Tra ve chuoi rong neu khong co -> dich ngay tai may (che do CPU binh thuong).
    """
    url = (os.getenv(GPU_URL_ENV) or "").strip()
    if url:
        return url.rstrip("/")

    # LUU Y: doc bang "utf-8-sig" de tu bo BOM. Notepad va PowerShell
    # (Set-Content -Encoding UTF8) deu ghi BOM vao dau file; neu khong bo thi dong
    # chu thich dau tien bi coi la URL -> loi "InvalidURL: Failed to parse".
    p = os.path.join(_BASE, GPU_URL_FILE)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip().lstrip("\ufeff").strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("http"):        # bo qua dong rac
                        return line.rstrip("/")
        except OSError:
            pass

    p = os.path.join(_BASE, ".env")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip().lstrip("\ufeff").strip()
                    if line.lower().startswith(GPU_URL_ENV.lower() + "="):
                        v = line.split("=", 1)[1].strip().strip("'\"")
                        if v.startswith("http"):
                            return v.rstrip("/")
        except OSError:
            pass
    return ""


def save_nmt_remote(url: str) -> str:
    """Luu dia chi may GPU vao gpu_url.txt de lan sau khong phai dan lai."""
    url = (url or "").strip().rstrip("/")
    p = os.path.join(_BASE, GPU_URL_FILE)
    with open(p, "w", encoding="utf-8") as f:
        f.write(f"# Dia chi may GPU thue (Kaggle/Colab/Modal). Doi moi phien thi sua file nay.\n")
        f.write(f"# De trong = dich ngay tai may (CPU).\n{url}\n")
    return url


def extract_gpu_url(text: str) -> str:
    """Trich dia chi may GPU tu mot doan van ban (vd dan ca log Kaggle/Colab).

    Vi moi phien Kaggle la mot URL khac, nguoi dung thuong copy ca dong log:
        "  URL CUA BAN:  https://abc-xyz.trycloudflare.com"
    Ham nay tim ra dung URL do, uu tien cac dich vu tunnel quen thuoc truoc khi
    lay URL https dau tien (vi trong log con co github.com, pypi.org...).
    """
    if not text:
        return ""
    for pat in (r"https?://[a-z0-9-]+\.trycloudflare\.com",
                r"https?://[a-z0-9-]+\.ngrok(?:-free)?\.(?:app|io)",
                r"https?://[a-z0-9-]+\.[a-z0-9-]+\.ts\.net"):
        m = re.search(pat, text, re.I)
        if m:
            return m.group(0).rstrip("/")
    # cuoi cung: URL http/https bat ky (vd may GPU tu dung trong LAN)
    m = re.search(r"https?://[A-Za-z0-9._:-]+", text)
    return m.group(0).rstrip("/") if m else ""


def check_remote(url: str, timeout: float = 8.0) -> dict:
    """Kiem tra may GPU con song va CO DUNG GPU khong.

    Tra ve {ok, engine, device, asr, loaded, error}. Dung de hien thi trang thai
    cho nguoi dung biet minh dang chay GPU hay CPU.
    """
    if not url:
        return {"ok": False, "error": "chua co dia chi may GPU"}
    try:
        import requests
        r = requests.get(url.rstrip("/") + "/health", timeout=timeout)
        r.raise_for_status()
        h = r.json() or {}
        nmt = h.get("nmt") or {}
        return {"ok": bool(h.get("loaded")), "loaded": h.get("loaded"),
                "engine": nmt.get("engine"), "device": nmt.get("device"),
                "asr": h.get("asr"), "error": h.get("error")}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "y")


def _env_float(name: str, default: float) -> float:
    try:
        v = os.getenv(name)
        return float(v) if v not in (None, "") else default
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        v = os.getenv(name)
        return int(v) if v not in (None, "") else default
    except Exception:
        return default


def _env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v not in (None, "") else default


@dataclass
class AppConfig:
    # ---------------- audio ----------------
    sample_rate: int = 16000

    # ---------------- ASR (Whisper) ----------------
    # asr_model        : model dung khi co GPU / khi chay online
    # asr_model_offline: model nhe dung khi CPU (may hop mat, laptop yeu)
    # ASR_MODEL (env) luon thang ca hai -> resolve_asr_model() quyet dinh
    asr_model: str = "large-v3-turbo"
    asr_model_offline: str = "tiny.en"
    asr_device: str = "auto"          # auto | cuda | cpu
    asr_compute: str = "auto"         # auto -> int8 (cpu) / int8_float16 (cuda)
    asr_beam: int = 1                 # streaming bat buoc = 1
    asr_language: str = "en"          # CHI tieng Anh
    asr_gate_rms: float = 0.004       # duoi nguong nay coi nhu im lang, khong goi ASR
    # VAD noi bo cua faster-whisper. Do thuc te: TAT nhanh hon ~15% va ket qua giong
    # (vi da co gate nang luong + loc hallucination rieng). Bat lai: ASR_VAD=1
    asr_vad_filter: bool = False

    # ---------------- chunking / endpointing (DON VI GIAY) ----------------
    # Moi client (mobile / desktop / extension) deu dung chung cac so nay,
    # khong con tinh theo "so chunk" -> hanh vi giong nhau tren moi thiet bi.
    partial_every_sec: float = 0.8    # nhip hien chu truc tiep
    partial_window_sec: float = 2.0   # cua so ASR cho partial
    final_silence_sec: float = 0.8    # im lang bao nhieu giay thi chot cau
    max_seg_sec: float = 8.0          # ep chot cau neu noi lien tuc qua lau
    overlap_keep_sec: float = 0.5     # giu lai duoi buffer sau khi chot (chong mat chu bien)
    max_buf_sec: float = 12.0         # tran buffer
    speak_rms: float = 0.008          # nguong coi la "dang noi" (endpointing)

    # ---------------- NMT (VinAI en2vi-v2) ----------------
    nmt_model: str = "vinai/vinai-translate-en2vi-v2"
    nmt_src: str = "en_XX"            # VinAI/mBART dung ma nay (khong phai eng_Latn)
    nmt_tgt: str = "vi_VN"
    nmt_max_len: int = 96
    nmt_live_beams: int = 1           # partial: nhanh nhat
    nmt_final_beams: int = 0          # 0 = auto (cuda 4 / cpu 2), hoac ACCURATE_BEAMS
    nmt_cache_size: int = 500
    ct2_dir: str = "models/ct2-en2vi-v2-int8"   # int8 CTranslate2 (nhanh 4-5x)

    # ---------------- TTS (giong Viet) ----------------
    offline: bool = False             # OFFLINE=1 -> khong goi mang
    confidential: bool = False        # CONFIDENTIAL=1 -> ep offline + khong lot du lieu
    tts_engine: str = "auto"          # auto | edge | offline
    tts_voice: str = "vi-VN-HoaiMyNeural"
    tts_rate: str = "+10%"
    tts_cache_size: int = 100
    tts_timeout_sec: float = 8.0      # tran thoi gian 1 lan synth (chong treo)
    piper_model: str = "models/piper/vi_VN-vais1000-medium.onnx"

    # ---------------- che do lam viec (Saydi: 3 mode -> ta ho tro 2) ----------------
    # translate : EN -> VI (mac dinh, co sub EN + sub VI)
    # transcribe: chi sub EN (khong dich, khong TTS)
    mode: str = "translate"

    # ---------------- phong / phien ----------------
    max_captions: int = 500           # tran so cau luu trong 1 phong
    session_ttl_hours: float = 4.0    # phong tu het han
    glossary_max_terms: int = 50      # Custom Dictionary (giong Saydi: toi da 50)
    target_e2e_sec: float = 2.0       # ngan sach do tre
    host: str = "http://localhost:8000"

    def __post_init__(self):
        # --- che do mat / offline ---
        if _env_bool("OFFLINE"):
            self.offline = True
        if _env_bool("CONFIDENTIAL"):
            # Hop mat: bat buoc offline (khong lot du lieu ra cloud)
            self.offline = True
            self.confidential = True
        if _env_bool("CONFIDENTIAL") and not os.getenv("MODE"):
            self.mode = "translate"

        # --- ghi de model ---
        if os.getenv("ASR_MODEL"):
            self.asr_model = os.getenv("ASR_MODEL")
        self.asr_model_offline = _env_str("ASR_MODEL_OFFLINE", self.asr_model_offline)
        # May thue GPU: co the ep thiet bi / kieu tinh toan (vd ASR_DEVICE=cuda,
        # ASR_COMPUTE=float16 khi GPU khong ho tro int8)
        self.asr_device = _env_str("ASR_DEVICE", self.asr_device)
        self.asr_compute = _env_str("ASR_COMPUTE", self.asr_compute)
        self.nmt_model = _env_str("NMT_MODEL", self.nmt_model)
        self.ct2_dir = _env_str("CT2_EN2VI", self.ct2_dir)

        # --- endpointing / nhip ---
        self.partial_every_sec = _env_float("PARTIAL_EVERY", self.partial_every_sec)
        self.partial_window_sec = _env_float("PARTIAL_WINDOW", self.partial_window_sec)
        self.final_silence_sec = _env_float("FINAL_SILENCE", self.final_silence_sec)
        self.max_seg_sec = _env_float("MAX_SEG", self.max_seg_sec)
        self.overlap_keep_sec = _env_float("OVERLAP_KEEP", self.overlap_keep_sec)
        self.max_buf_sec = _env_float("MAX_BUF", self.max_buf_sec)
        self.speak_rms = _env_float("SPEAK_RMS", self.speak_rms)
        self.asr_gate_rms = _env_float("ASR_GATE_RMS", self.asr_gate_rms)
        self.asr_vad_filter = _env_bool("ASR_VAD", self.asr_vad_filter)

        # --- NMT beams ---
        if os.getenv("ACCURATE_BEAMS"):
            self.nmt_final_beams = _env_int("ACCURATE_BEAMS", self.nmt_final_beams)

        # --- TTS ---
        self.tts_engine = _env_str("TTS_ENGINE", self.tts_engine)
        if self.tts_engine == "auto":
            self.tts_engine = "offline" if self.offline else "edge"
        if self.offline and self.tts_engine == "edge":
            # offline ma van doi edge -> ep ve offline cho dung nghia "khong can mang"
            self.tts_engine = "offline"

        # --- phong / phien ---
        self.max_captions = _env_int("MAX_CAPTIONS", self.max_captions)
        self.session_ttl_hours = _env_float("SESSION_TTL_HOURS", self.session_ttl_hours)
        self.glossary_max_terms = _env_int("GLOSSARY_MAX", self.glossary_max_terms)
        self.host = _env_str("SERVER_HOST", self.host)

        # --- mode ---
        m = _env_str("MODE", self.mode).strip().lower()
        self.mode = m if m in ("translate", "transcribe") else "translate"

    # ------------------------------------------------------------------
    def resolve_asr_model(self, use_cuda: bool) -> str:
        """Chon model ASR theo phan cung. ASR_MODEL (env) luon duoc uu tien.

        Truoc day desktop luon bi ep tiny.en vi script tu set ASR_MODEL -> may co GPU
        van chay model nho nhat. Gio: khong co env => GPU dung turbo, CPU dung tiny.en.

        Neu trong `models/` da co ban tai san -> dung ban do, khoi can cache HuggingFace
        (dieu kien de may hop mat chay offline that su).
        """
        forced = os.getenv("ASR_MODEL")
        name = forced or (self.asr_model if use_cuda else self.asr_model_offline)
        return local_model_dir(name) or name

    def resolve_nmt_path(self) -> str:
        """Duong dan model NMT: uu tien ban trong models/, nguoc lai dung ID HuggingFace."""
        return local_model_dir(self.nmt_model) or self.nmt_model


    def resolve_final_beams(self, use_cuda: bool) -> int:
        """Beam cho cau FINAL.

        CPU = 1 (greedy): do thuc te cho thay VinAI 448M fp32 tren CPU ton ~2-3 PHUT
        cho 1 cau voi beam=2 -> khong the dung realtime. Beam cao chi hop ly khi co GPU
        hoac khi da convert sang CT2 int8 (nhanh 4-5x). Dat ACCURATE_BEAMS=2 neu muon.
        """
        if self.nmt_final_beams > 0:
            return self.nmt_final_beams
        return 4 if use_cuda else 1

    def resolve_compute(self, use_cuda: bool) -> str:
        if self.asr_compute != "auto":
            return self.asr_compute
        return "int8_float16" if use_cuda else "int8"

    def as_dict(self) -> dict:
        return {
            "sample_rate": self.sample_rate,
            "asr_model": self.asr_model,
            "asr_model_offline": self.asr_model_offline,
            "nmt_model": self.nmt_model,
            "ct2_dir": self.ct2_dir,
            "offline": self.offline,
            "confidential": self.confidential,
            "tts_engine": self.tts_engine,
            "mode": self.mode,
            "partial_every_sec": self.partial_every_sec,
            "final_silence_sec": self.final_silence_sec,
            "max_seg_sec": self.max_seg_sec,
            "speak_rms": self.speak_rms,
            "target_e2e_sec": self.target_e2e_sec,
            "glossary_max_terms": self.glossary_max_terms,
        }


DEFAULT = AppConfig()

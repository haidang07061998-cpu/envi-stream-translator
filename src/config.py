"""Cau hinh TAP TRUNG cho toan he thong (chi 1 cap ngon ngu: EN -> VI).

Day la NGUON DUY NHAT cho moi tham so. Server, desktop, gradio deu doc tu day,
khong hardcode so o trong app nua. Moi tham so deu ghi de duoc bang bien moi truong.

Vi du:
    set OFFLINE=1 & set CONFIDENTIAL=1 & set ASR_MODEL=tiny.en
    set PARTIAL_EVERY=0.6 & set FINAL_SILENCE=0.6 & set MODE=translate
"""
from dataclasses import dataclass
import os


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
    asr_vad_filter: bool = True       # VAD noi bo cua faster-whisper (finalize)

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
        """
        forced = os.getenv("ASR_MODEL")
        if forced:
            return forced
        return self.asr_model if use_cuda else self.asr_model_offline

    def resolve_final_beams(self, use_cuda: bool) -> int:
        if self.nmt_final_beams > 0:
            return self.nmt_final_beams
        return 4 if use_cuda else 2

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

"""Xu ly streaming EN -> VI (kieu incremental cascaded, khong phai simultaneous that).

Luong:
- partial: ASR tren cua so truot moi `partial_every_sec` -> hien chu ngay (~0.3-0.5s)
- final  : khi im lang `final_silence_sec` hoac qua `max_seg_sec` -> chot cau,
           dich lai chuan (beam cao) + TTS. Partial chi hien chu, TTS chi doc khi final.

Sua loi quan trong so voi ban cu:
1. `_clean_en` cu dung `startswith("you ")` -> XOA TRANG moi cau bat dau bang "You ..."
   (rat pho bien trong hop). Gio chi khop CHINH XAC cau hallucination hoac cau lap tu.
2. `push()` cu khong co gate nang luong -> chay ASR ca khi im lang (ton CPU + bia chu).
3. Chot cau cu lay ca buffer nen 0.5-0.8s duoi bi dich lai -> lap tu o dau cau.
   Gio `strip_overlap()` cat phan da hien.
4. Moi thao tac buffer deu qua `self.lock`.
"""
import time
import threading
import numpy as np

# Cau Whisper hay "bia" khi gap im lang / nhac nen. CHI khop chinh xac ca cau.
_HALLUCINATION_EXACT = {
    "thank you for watching", "thanks for watching", "thank you for watching!",
    "thank you very much", "thank you so much", "please subscribe",
    "subscribe to my channel", "like and subscribe", "music", "music playing",
    "subtitle", "subtitles", "subtitle by", "subtitles by", "amara.org",
    "transcription by", "translated by", "www.amara.org", "...", "♪", "♪♪",
}
# Token nhieu don le: chi bi xoa khi CA CAU chi co dung token do.
_NOISE_ONLY = {"you", "uh", "um", "hmm", "huh", "mm", "mhm", "ah", "eh", "oh", "er", "hm"}
# Tien to "ghi cong" cua phu de YouTube: khong bao gio la cau noi trong cuoc hop.
_HALLUCINATION_PREFIXES = ("subtitles by", "subtitle by", "transcription by",
                           "translated by", "amara.org", "www.amara.org",
                           "subs by", "captions by")


def _norm(t: str) -> str:
    return " ".join(t.lower().replace("♪", " ").split()).strip(" .,!?-…:;")


def _clean_en(text: str) -> str:
    """Loc hallucination nhung KHONG duoc xoa cau hop le.

    - khop chinh xac cau hallucination -> bo
    - ca cau chi la 1 token nhieu (uh/hmm/you) -> bo
    - ca cau lap cung 1-2 tu ("you you you you") -> bo
    - con lai: giu nguyen, ke ca "You should check the API latency..."
    """
    t = (text or "").strip()
    if not t:
        return ""
    n = _norm(t)
    if not n:
        return ""
    if n in _HALLUCINATION_EXACT:
        return ""
    if n.startswith(_HALLUCINATION_PREFIXES):
        return ""
    words = t.split()
    bare = [w.lower().strip(".,!?-…:;") for w in words]
    if len(bare) == 1 and bare[0] in _NOISE_ONLY:
        return ""
    if len(bare) >= 4 and len(set(bare)) == 1:
        return ""
    if len(bare) >= 6 and len(set(bare)) <= 2:
        return ""
    return t


def strip_overlap(prev: str, new: str, max_words: int = 14) -> str:
    """Cat phan dau cua `new` da xuat hien o CUOI `prev` (do buffer giu overlap).

    Vi du: prev="the latency is too high" + new="too high for mobile clients"
           -> "for mobile clients"
    """
    if not prev or not new:
        return new
    pw = [w.lower().strip(".,!?-") for w in prev.split()]
    nw = new.split()
    nwl = [w.lower().strip(".,!?-") for w in nw]
    limit = min(len(pw), len(nw), max_words)
    for k in range(limit, 0, -1):
        if pw[-k:] == nwl[:k]:
            return " ".join(nw[k:]).strip()
    return new


class SimultaneousProcessor:
    def __init__(self, asr, nmt, tts=None, sr=16000,
                 partial_every_sec=0.8, partial_window_sec=2.0,
                 overlap_keep_sec=0.5, max_buf_sec=12.0,
                 speak_rms=0.008, gate_rms=0.004, mode="translate"):
        self.asr, self.nmt, self.tts = asr, nmt, tts
        self.sr = sr
        self.partial_every = partial_every_sec
        self.partial_window = partial_window_sec
        self.buf = np.zeros(0, dtype=np.float32)
        self.last_emit = time.time()
        self.last_final_text = ""
        self._last_partial = ""
        self.lock = threading.Lock()
        self.overlap_keep = int(overlap_keep_sec * sr)
        self.maxn = int(max_buf_sec * sr)
        self.speak_rms = speak_rms
        self.gate_rms = gate_rms
        self.mode = mode
        self.last_voice = time.time()

    # ------------------------------------------------------------------ buffer
    def _push_buf(self, chunk: np.ndarray):
        with self.lock:
            self.buf = np.concatenate([self.buf, chunk])
            if len(self.buf) > self.maxn:
                self.buf = self.buf[-self.maxn:]

    def _take_segment(self, keep_overlap=True):
        """Lay segment de finalize (thread-safe). Giu duoi overlap de khong mat chu bien."""
        with self.lock:
            if len(self.buf) == 0:
                return None
            seg = self.buf.copy()
            if keep_overlap and self.overlap_keep > 0 and len(self.buf) > self.overlap_keep:
                self.buf = self.buf[-self.overlap_keep:]
            else:
                self.buf = np.zeros(0, dtype=np.float32)
            return seg

    def _window(self, seconds: float):
        with self.lock:
            n = int(self.sr * seconds)
            return self.buf[-n:].copy() if len(self.buf) else np.zeros(0, dtype=np.float32)

    @staticmethod
    def _rms(a) -> float:
        return float((a ** 2).mean() ** 0.5) if a is not None and len(a) else 0.0

    def reset(self):
        with self.lock:
            self.buf = np.zeros(0, dtype=np.float32)
        self.last_final_text = ""
        self._last_partial = ""
        self.last_emit = time.time()

    # ------------------------------------------------------------------ partial
    def push(self, chunk: np.ndarray):
        """Nhan PCM 16k float32 -> event partial (co ban dich) hoac None."""
        self._push_buf(chunk)
        now = time.time()
        if now - self.last_emit < self.partial_every:
            return None
        self.last_emit = now
        win = self._window(self.partial_window)
        if self._rms(win) < self.gate_rms:      # im lang -> khong goi ASR
            return None
        r = self.asr.transcribe(win, self.sr)
        en = _clean_en(r["text"])
        if not en or en == self.last_final_text:
            return None
        ev = {"kind": "partial", "en": en, "vi": None, "nmt_ms": 0.0,
              "asr_ms": r["asr_ms"], "unstable": True,
              "e2e_ms": r["asr_ms"]}
        if self.mode == "translate" and self.nmt is not None:
            vi, nmt_ms = self.nmt.translate(en)
            ev["vi"] = vi
            ev["nmt_ms"] = nmt_ms
            ev["e2e_ms"] = r["asr_ms"] + nmt_ms
        return ev

    def add_audio(self, chunk: np.ndarray):
        """Chi append buffer, KHONG goi model — dung cho vong lap nhan audio cua server.

        Server phai doc socket that nhanh; neu goi ASR ngay trong vong lap thi
        uvicorn/websockets se ngat ket noi khi hang doi phia server phinh ra.
        """
        self._push_buf(chunk)

    def take_partial_window(self):
        """Lay cua so de chay partial (thread-safe). None neu im lang / qua ngan.

        Tach khoi `push_fast` de server co the chay ASR o TASK NEN: vong lap nhan audio
        phai luon nhanh, neu khong uvicorn se ngat ket noi khi buffer day.
        """
        win = self._window(self.partial_window)
        if win is None or len(win) < int(self.sr * 0.3):
            return None
        if self._rms(win) < self.gate_rms:
            return None
        return win

    def accept_partial(self, text: str):
        """Loc + dedup ket qua partial. Tra ve chuoi da sach hoac None neu bo qua."""
        en = _clean_en(text)
        if not en or en == self.last_final_text or en == self._last_partial:
            return None
        self._last_partial = en
        return en

    def push_fast(self, chunk: np.ndarray):
        """Realtime cho CPU yeu: chi ASR (~0.2s), khong dich. NMT chay worker rieng."""
        self._push_buf(chunk)
        now = time.time()
        if now - self.last_emit < self.partial_every:
            return None
        self.last_emit = now
        win = self.take_partial_window()
        if win is None:
            return None
        r = self.asr.transcribe(win, self.sr)
        en = self.accept_partial(r["text"])
        if not en:
            return None
        return {"kind": "partial", "en": en, "asr_ms": r["asr_ms"], "unstable": True}

    # ------------------------------------------------------------------ finalize
    def finalize_text(self, with_audio: bool = False):
        """Chot cau CHI ASR (nhanh), NMT+TTS de worker nen dich sau.

        Giu overlap + cat phan da hien -> khong lap tu o dau cau.
        with_audio=True: tra kem "_audio" (segment) de tinh dac trung nguoi noi,
        caller phai pop key nay truoc khi gui ra ngoai.
        """
        seg = self._take_segment(keep_overlap=True)
        if seg is None or len(seg) < int(self.sr * 0.3):
            return None
        if self._rms(seg) < self.gate_rms:
            return None
        a = self.asr.transcribe(seg, self.sr)
        en = _clean_en(a["text"])
        if not en:
            return None
        en = strip_overlap(self.last_final_text, en)
        if not en or en == self.last_final_text:
            return None
        self.last_final_text = en
        self._last_partial = ""
        out = {"kind": "final", "en": en, "asr_ms": a["asr_ms"], "unstable": False}
        if with_audio:
            out["_audio"] = seg
        return out

    def finalize(self):
        """Chot cau day du: ASR + NMT (beam cao) + TTS. Dung khi co TTS/khong co worker nen."""
        seg = self._take_segment(keep_overlap=True)
        if seg is None or len(seg) < int(self.sr * 0.3):
            return None
        if self._rms(seg) < self.gate_rms:
            return None
        t0 = time.time()
        a = self.asr.transcribe(seg, self.sr)
        en = _clean_en(a["text"])
        if not en:
            return None
        en = strip_overlap(self.last_final_text, en)
        if not en:
            return None
        self.last_final_text = en
        self._last_partial = ""
        fin = {"kind": "final", "en": en, "asr_ms": a["asr_ms"],
               "nmt_ms": 0.0, "tts_ms": 0.0, "vi": None, "audio_vi": None,
               "unstable": False}
        if self.mode == "translate" and self.nmt is not None:
            vi, nmt_ms = self.nmt.translate(en, accurate=True)
            fin["vi"], fin["nmt_ms"] = vi, nmt_ms
            if self.tts is not None:
                t = self.tts.synth(vi)
                fin["audio_vi"], fin["tts_ms"] = t["audio"], t["tts_ms"]
        fin["e2e_ms"] = (time.time() - t0) * 1000
        return fin

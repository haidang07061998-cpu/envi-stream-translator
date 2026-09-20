"""Phien live 2 man hinh (kieu Saydi, CHI 1 cap ngon ngu: EN -> VI).

Trach nhiem:
- nhan PCM 16k, tra ve partial (chu chay)
- chot cau (final): ASR nhanh -> tra EN + nhan nguoi noi ngay; NMT/TTS de worker nen
- gan ngu canh (scenario + thuat ngu) cho CA ASR (initial_prompt) va NMT (glossary)
- nhan nguoi noi ON DINH qua SpeakerTracker (khong hoan vai nhu KMeans fit lai)

Sua loi ban cu:
- `finalize()` copy `self.sim.buf` roi gan lai KHONG qua lock -> race voi luong mic.
  Gio moi thu di qua `sim._take_segment()` (co lock).
- `finalize_fast()` khong dedup overlap -> lap tu o dau cau. Gio di qua `finalize_text()`.
- Khong co `mode`: gio ho tro translate | transcribe.
"""
import time

from .config import DEFAULT


class LiveSession:
    def __init__(self, asr, nmt, tts=None, sr=16000, sid=None, ctx=None,
                 mode=None, partial_every_sec=None, max_k=4, cfg=None):
        from .context_engine import ContextEngine
        from .simultaneous import SimultaneousProcessor
        from .diarization import SpeakerTracker

        self.cfg = cfg or DEFAULT
        self.sr = sr
        self.sid = sid
        self.mode = (mode or self.cfg.mode)
        if self.mode not in ("translate", "transcribe"):
            self.mode = "translate"
        self.ctx = ctx or ContextEngine("event", auto=True)
        self.sim = SimultaneousProcessor(
            asr, nmt, tts, sr,
            partial_every_sec=(partial_every_sec if partial_every_sec is not None
                               else self.cfg.partial_every_sec),
            partial_window_sec=self.cfg.partial_window_sec,
            overlap_keep_sec=self.cfg.overlap_keep_sec,
            max_buf_sec=self.cfg.max_buf_sec,
            speak_rms=self.cfg.speak_rms,
            gate_rms=self.cfg.asr_gate_rms,
            mode=self.mode)
        self.speakers = SpeakerTracker(max_k=max_k, sr=sr)
        self.n_speakers = 1
        self._cap_id = 0
        self.apply_context()

    # ------------------------------------------------------------- ngu canh
    def apply_context(self):
        """Nap ten rieng/thuat ngu vao ASR + NMT. Goi lai moi khi doi ngu canh."""
        try:
            self.sim.asr.set_prompt(self.ctx.asr_prompt())
        except Exception:
            pass
        try:
            if self.sim.nmt is not None and self.mode == "translate":
                self.sim.nmt.set_glossary(self.ctx.glossary())
        except Exception:
            pass

    def set_context(self, scenario=None, details=None, keywords=None, terms=None,
                    replace_terms=True):
        if scenario:
            self.ctx.set_scenario(scenario)
        if details is not None or keywords is not None:
            self.ctx.set_meeting(details if details is not None else self.ctx.details,
                                 keywords if keywords is not None else self.ctx.keywords)
        if terms:
            if replace_terms:
                self.ctx.clear_custom()
            self.ctx.add_terms(terms)
        self.apply_context()
        return {"scenario": self.ctx.scenario,
                "terms": len(self.ctx.glossary()),
                "asr_prompt": bool(self.ctx.asr_prompt())}

    # ------------------------------------------------------------- audio
    def push(self, chunk):
        return self.sim.push(chunk)

    def _label(self, audio):
        try:
            i, k = self.speakers.assign(audio)
            self.n_speakers = k
            return f"Speaker {i + 1}"
        except Exception:
            return "Speaker 1"

    def next_id(self) -> int:
        self._cap_id += 1
        return self._cap_id

    # ------------------------------------------------------------- chot cau
    def finalize_text(self):
        """Chot cau nhanh (chi ASR) -> EN + speaker + id. NMT/TTS lam sau o worker."""
        fin = self.sim.finalize_text(with_audio=True)
        if not fin:
            return None
        audio = fin.pop("_audio", None)
        fin["speaker"] = self._label(audio)
        fin["n_speakers"] = self.n_speakers
        fin["scenario"] = self.ctx.scenario
        fin["mode"] = self.mode
        fin["id"] = self.next_id()
        fin["vi"] = None
        fin["nmt_ms"] = 0.0
        return fin

    # giu ten cu cho desktop_app_v2
    def finalize_fast(self):
        return self.finalize_text()

    def translate(self, en, accurate=True):
        """Worker nen goi: dich 1 cau EN -> (vi, ms, info)."""
        if self.mode != "translate" or self.sim.nmt is None:
            return "", 0.0, {"scenario": self.ctx.scenario, "terms_applied": 0,
                             "numbers_missing": []}
        return self.ctx.translate(en, self.sim.nmt, accurate=accurate)

    def speak(self, vi):
        """Tong hop giong Viet -> (audio_bytes|None, tts_ms)."""
        if self.sim.tts is None or not vi:
            return None, 0.0
        try:
            t = self.sim.tts.synth(vi)
            return t.get("audio"), float(t.get("tts_ms", 0.0) or 0.0)
        except Exception:
            return None, 0.0

    def finalize(self):
        """Chot cau day du (ASR + NMT + TTS) - dung khi khong co worker nen."""
        fin = self.finalize_text()
        if not fin:
            return None
        t0 = time.time()
        vi, nmt_ms, info = self.translate(fin["en"], accurate=True)
        fin["vi"], fin["nmt_ms"] = vi, nmt_ms
        fin["scenario"] = info.get("scenario", fin["scenario"])
        fin["numbers_missing"] = info.get("numbers_missing", [])
        audio, tts_ms = self.speak(vi)
        fin["audio_vi"], fin["tts_ms"] = audio, tts_ms
        fin["e2e_ms"] = float(fin.get("asr_ms", 0.0)) + (time.time() - t0) * 1000
        return fin

    def stats(self) -> dict:
        return {"mode": self.mode, "scenario": self.ctx.scenario,
                "terms": len(self.ctx.glossary()), "n_speakers": self.n_speakers,
                "captions": self._cap_id,
                "asr_prompt": bool(self.ctx.asr_prompt())}

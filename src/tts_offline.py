"""TTS offline 100% thay Edge-TTS (can mang).
Luong van giu: EN mic -> sub EN (man hinh 1) -> dich VI (man hinh 2) -> doc VI + xuat txt.
Thu tu uu tien:
1. Piper (onnx vi_VN, nhe ~60MB, hay nhat offline)
2. pyttsx3 / SAPI5 Windows (san co, khong can model)
3. Silent (tra audio=None, van hien chu + xuat file binh thuong).
Interface giong EdgeTTSWrapper: synth(text) -> {audio, tts_ms, cached}
audio la bytes WAV (khong phai mp3) de web <audio> phat duoc offline.
"""
import time
import io
import wave
from collections import OrderedDict


class OfflineTTSWrapper:
    def __init__(self, model_path=None, cache_size=100, sample_rate=22050):
        self.cache = OrderedDict()
        self.cache_size = cache_size
        self.sr = sample_rate
        self.backend = "silent"
        self.voice = None
        self._pyttsx3_engine = None

        # 1. Thu Piper neu co model
        if model_path:
            try:
                from piper import PiperVoice
                import os
                if os.path.exists(model_path):
                    self.voice = PiperVoice.load(model_path)
                    self.backend = "piper"
                    print(f"[TTS-offline] dung Piper: {model_path}")
            except Exception as e:
                print(f"[TTS-offline] khong tai duoc Piper ({e}), thu SAPI5...")

        # 2. Fallback pyttsx3 / SAPI5 (Windows offline san co)
        if self.backend == "silent":
            try:
                import pyttsx3
                eng = pyttsx3.init()
                # giam toc do chut cho ro tieng Viet
                try:
                    eng.setProperty("rate", 165)
                except Exception:
                    pass
                self._pyttsx3_engine = eng
                self.backend = "sapi5"
                print("[TTS-offline] dung pyttsx3/SAPI5 (offline Windows)")
            except Exception as e:
                print(f"[TTS-offline] khong co pyttsx3 ({e}) -> che do silent (van hien chu + xuat txt)")

    def _get(self, k):
        if k in self.cache:
            self.cache.move_to_end(k)
            return self.cache[k]
        return None

    def _put(self, k, v):
        self.cache[k] = v
        self.cache.move_to_end(k)
        if len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)

    def _piper_synth(self, text: str) -> bytes | None:
        """Piper -> WAV bytes 16-bit mono.

        API Piper doi giua cac ban: ban moi tu ghi header WAV, ban cu can set tham so
        truoc. Thu ban moi truoc, fallback ban cu.
        """
        import io as _io
        import wave as _wave
        buf = _io.BytesIO()
        try:
            with _wave.open(buf, "wb") as wav:
                self.voice.synthesize(text, wav)
            data = buf.getvalue()
            if data and len(data) > 44:
                return data
        except Exception:
            pass
        buf = _io.BytesIO()
        with _wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(getattr(getattr(self.voice, "config", None),
                                     "sample_rate", self.sr))
            self.voice.synthesize(text, wav)
        return buf.getvalue()

    def _sapi5_synth(self, text: str) -> bytes | None:
        """pyttsx3 -> WAV bytes. Chay tren thread rieng, file tam."""
        import tempfile
        import os
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            self._pyttsx3_engine.save_to_file(text, path)
            self._pyttsx3_engine.runAndWait()
            with open(path, "rb") as f:
                return f.read()
        except Exception as e:
            print(f"[TTS-offline] sapi5 loi: {e}")
            return None
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def synth(self, text: str, out_path: str | None = None):
        text = (text or "").strip()
        if not text:
            return {"audio": None, "tts_ms": 0, "cached": False, "error": None}
        key = f"offline|{self.backend}|{text}"
        hit = self._get(key)
        t0 = time.time()
        err = None
        if hit is not None:
            audio, cached = hit, True
        else:
            audio, cached = None, False
            try:
                if self.backend == "piper":
                    audio = self._piper_synth(text)
                elif self.backend == "sapi5":
                    audio = self._sapi5_synth(text)
                else:
                    audio = None  # silent: van giu luong chu + export
                    err = "backend=silent (khong co Piper/SAPI5)"
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                print(f"[TTS-offline] loi synth ({self.backend}): {e}")
                audio = None
            if audio:
                self._put(key, audio)
        ms = (time.time() - t0) * 1000
        if audio and out_path:
            with open(out_path, "wb") as f:
                f.write(audio)
        return {"audio": audio, "tts_ms": ms, "cached": cached, "error": err}

"""ASR tieng Anh (faster-whisper) toi uu cho streaming.

Ho tro `initial_prompt`: nap truoc ten rieng / thuat ngu cua cuoc hop de Whisper
nghieng ve dung tu chuyen nganh (tuong duong "Meeting Details & Keywords" cua Saydi).
"""
import time
import numpy as np

from .config import local_model_dir


class FasterWhisperASR:
    """Wrapper Faster-Whisper toi uu cho streaming realtime (chi tieng Anh)."""

    def __init__(self, model_size="large-v3-turbo", device="auto",
                 compute_type="auto", beam_size=1, language="en",
                 vad_filter=True, vad_params=None, initial_prompt=None,
                 gate_rms=0.004):
        from faster_whisper import WhisperModel
        import torch
        # Uu tien ban model da tai san trong models/ -> chay offline that su,
        # khong phu thuoc cache HuggingFace.
        self.requested_model = model_size
        local = local_model_dir(model_size)
        if local:
            model_size = local
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if compute_type == "auto":
            compute_type = "int8_float16" if device == "cuda" else "int8"
        self.model = WhisperModel(model_size, device=device,
                                  compute_type=compute_type)
        self.beam = beam_size
        self.lang = language
        self.vad_filter = vad_filter
        self.gate_rms = gate_rms
        self.vad_params = vad_params or {
            "min_silence_duration_ms": 600,
            "speech_pad_ms": 250,
            "min_speech_duration_ms": 250,
            "threshold": 0.5,
        }
        self.device = device
        self.model_size = model_size
        self.initial_prompt = (initial_prompt or "").strip() or None
        self._prompt_supported = True

    # ------------------------------------------------------------------
    def set_prompt(self, prompt):
        """Nap ten rieng / thuat ngu cho phien (goi khi bat dau cuoc hop)."""
        self.initial_prompt = (prompt or "").strip() or None

    def transcribe(self, audio: np.ndarray, sr=16000, initial_prompt=None,
                   vad_filter=None):
        """vad_filter=None -> dung cau hinh; False -> tat VAD cho lan goi nay.

        Partial nen TAT VAD: cua so 2s ma chay VAD cua Whisper la ton them 20-40% CPU
        trong khi ngoai kia da co gate nang luong.
        """
        # gate im lang: bo qua transcribe, tiet kiem CPU + chong hallucinate
        if audio is None or len(audio) < int(sr * 0.2):
            return {"text": "", "asr_ms": 0.0}
        try:
            rms = float((audio ** 2).mean() ** 0.5)
            if rms < self.gate_rms:
                return {"text": "", "asr_ms": 0.0}
        except Exception:
            pass

        prompt = (initial_prompt if initial_prompt is not None
                  else self.initial_prompt)
        prompt = (prompt or "").strip() or None
        use_vad = self.vad_filter if vad_filter is None else bool(vad_filter)

        kwargs = dict(
            language=self.lang,
            beam_size=self.beam,
            condition_on_previous_text=False,   # bat buoc False khi streaming
            vad_filter=use_vad,
            word_timestamps=False,
            temperature=0.0,
        )
        if use_vad:
            kwargs["vad_parameters"] = self.vad_params
        t0 = time.time()
        segments = None
        if prompt and self._prompt_supported:
            try:
                segments, _ = self.model.transcribe(audio, initial_prompt=prompt, **kwargs)
            except TypeError:
                # ban faster-whisper cu khong ho tro initial_prompt -> tat han
                self._prompt_supported = False
            except Exception:
                pass
        if segments is None:
            segments, _ = self.model.transcribe(audio, **kwargs)
        texts = [s.text.strip() for s in segments]
        text = " ".join(t for t in texts if t).strip()
        return {"text": text, "asr_ms": (time.time() - t0) * 1000}

    def transcribe_file(self, path: str):
        from .audio_utils import load_audio_16k
        audio = load_audio_16k(path)
        return self.transcribe(audio)

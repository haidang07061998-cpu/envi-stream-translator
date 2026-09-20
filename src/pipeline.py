import time
import numpy as np

class CascadedPipeline:
    """Streaming Audio -> VAD -> ASR -> NMT -> TTS. Do latency tung khau."""
    def __init__(self, asr, nmt, tts, sr=16000, target_e2e=2.0):
        self.asr, self.nmt, self.tts = asr, nmt, tts
        self.sr = sr
        self.target = target_e2e
        self.captions = []  # live caption buffer [{en, vi, t}]

    def process_segment(self, audio: np.ndarray):
        r = {"en": "", "vi": "", "asr_ms": 0, "nmt_ms": 0, "tts_ms": 0,
             "e2e_ms": 0, "audio_vi": None, "cached_tts": False}
        t0 = time.time()
        a = self.asr.transcribe(audio, self.sr)
        r["en"], r["asr_ms"] = a["text"], a["asr_ms"]
        if not r["en"]:
            return r
        vi, nmt_ms = self.nmt.translate(r["en"])
        r["vi"], r["nmt_ms"] = vi, nmt_ms
        t = self.tts.synth(r["vi"])
        r["audio_vi"], r["tts_ms"], r["cached_tts"] = t["audio"], t["tts_ms"], t["cached"]
        r["e2e_ms"] = (time.time()-t0)*1000
        r["realtime_ok"] = r["e2e_ms"]/1000 <= self.target
        self.captions.append({"en": r["en"], "vi": r["vi"]})
        return r

    def process_file(self, path: str, save_tts_prefix: str | None = None):
        from .audio_utils import load_audio_16k, energy_vad
        audio = load_audio_16k(path)
        segs = energy_vad(audio, self.sr)
        # Gop cac doan VAD gan nhau (gap <0.8s) thanh nhom 2-8s:
        # - Whisper chay full cua so 30s nen goi nhieu lan cho manh vun <1s vua cham vua mat ngu canh NMT
        groups = []
        for s, e in segs:
            if groups and s - groups[-1][1] < 0.8 and e - groups[-1][0] < 8.0:
                groups[-1][1] = e
            else:
                groups.append([s, e])
        results = []
        for i, (s, e) in enumerate(groups):
            chunk = audio[int(s*self.sr):int(e*self.sr)]
            r = self.process_segment(chunk)
            r.update({"seg": i, "start": s, "end": e})
            if save_tts_prefix and r["audio_vi"]:
                with open(f"{save_tts_prefix}_seg{i}.mp3", "wb") as f:
                    f.write(r["audio_vi"])
            results.append(r)
        return results

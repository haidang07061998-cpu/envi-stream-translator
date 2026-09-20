import numpy as np

TARGET_SR = 16000

def resample_to_16k(buf, from_sr, to_sr=16000):
    """Resample mono float32 -> 16k. Ưu tiên resample_poly (anti-alias), fallback interp."""
    import numpy as np
    if buf is None or len(buf) == 0:
        return np.zeros(0, dtype=np.float32)
    buf = np.asarray(buf, dtype=np.float32)
    if from_sr == to_sr:
        return buf
    try:
        from scipy.signal import resample_poly
        import math
        g = math.gcd(int(from_sr), int(to_sr))
        return resample_poly(buf, int(to_sr // g), int(from_sr // g)).astype(np.float32)
    except Exception:
        try:
            import librosa
            return librosa.resample(buf, orig_sr=from_sr, target_sr=to_sr).astype(np.float32)
        except Exception:
            ratio = float(from_sr) / float(to_sr)
            n_new = int(len(buf) / ratio)
            if n_new <= 0:
                return np.zeros(0, dtype=np.float32)
            x_old = np.linspace(0, 1, len(buf))
            x_new = np.linspace(0, 1, n_new)
            return np.interp(x_new, x_old, buf).astype(np.float32)

def load_audio_16k(path: str) -> np.ndarray:
    """Load bat ky file audio -> mono 16kHz float32. Dung librosa neu co, fallback soundfile."""
    try:
        import librosa
        y, _ = librosa.load(path, sr=TARGET_SR, mono=True)
        return y.astype(np.float32)
    except Exception:
        import soundfile as sf
        y, sr = sf.read(path, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=-1)
        if sr != TARGET_SR:
            # resample don gian bang noi suy tuyen tinh neu thieu librosa
            import math
            dur = len(y) / sr
            n_new = int(dur * TARGET_SR)
            x_old = np.linspace(0, 1, len(y))
            x_new = np.linspace(0, 1, n_new)
            y = np.interp(x_new, x_old, y).astype(np.float32)
        return y

def split_with_overlap(audio: np.ndarray, chunk_sec=4.0, overlap_sec=0.5, sr=16000):
    n_chunk = int(chunk_sec * sr)
    n_ov = int(overlap_sec * sr)
    step = max(1, n_chunk - n_ov)
    out = []
    for s in range(0, len(audio), step):
        e = min(len(audio), s + n_chunk)
        out.append(audio[s:e])
        if e >= len(audio):
            break
    return out

def energy_vad(audio: np.ndarray, sr=16000, frame_ms=30, thresh_db=-40.0):
    """VAD don gian dua tren nang luong de chay duoc ca khi thieu torch/silero.
    Tra ve list (start_sec, end_sec) co tieng noi."""
    fl = int(sr * frame_ms / 1000)
    if len(audio) < fl:
        return [(0.0, len(audio) / sr)] if len(audio) else []
    frames = [audio[i:i+fl] for i in range(0, len(audio)-fl+1, fl)]
    rms = np.array([np.sqrt(np.mean(f*f)+1e-10) for f in frames])
    db = 20*np.log10(rms+1e-10)
    speech = db > thresh_db
    segs, s = [], None
    for i, v in enumerate(speech):
        if v and s is None:
            s = i
        if (not v or i == len(speech)-1) and s is not None:
            e = i if not v else i+1
            # loc doan qua ngan <0.3s
            if (e-s)*frame_ms/1000 >= 0.3:
                segs.append((s*frame_ms/1000, e*frame_ms/1000))
            s = None
    return segs if segs else [(0.0, len(audio)/sr)]

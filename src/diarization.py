"""Speaker diarization nhe cho EN -> VI.

Van de cua ban cu:
1. `diarize_auto` fit lai KMeans tren TOAN BO tap dac trung moi khi co cau moi -> chi so
   cluster doi giua cac lan goi -> "Speaker 1" va "Speaker 2" hoan vai cho nhau.
2. `label_speakers` tao dac trung bang `np.random.randn` (du lieu GIA) -> nhan ngau nhien.
3. `librosa.feature.mfcc` **TREO >180 giay** tren may nay (numba JIT) -> `LiveSession.
   finalize_text()` goi `_mfcc_mean()` de gan nhan nguoi noi nen KHONG BAO GIO tra ve
   => khong co cau final nao, khong co caption nao. Xem `_mfcc_mean` ben duoi: da thay
   bang dac trung log-mel THUAN NUMPY (chay ~ms).

Nguong hieu chinh bang bien moi truong SPEAKER_THRESHOLD (mac dinh 0.60).
"""
import os
import numpy as np


def _mel_edges(n_mels=13, sr=16000, fmin=50.0, fmax=7600.0):
    """Chi so bin FFT cho cac dai mel (thuan numpy)."""
    def hz2mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel2hz(m):
        return 700.0 * (10.0 ** (m / 2595.0) - 1.0)

    mels = np.linspace(hz2mel(fmin), hz2mel(fmax), n_mels + 2)
    hz = mel2hz(mels)
    n_bins = 1 + 256                       # rfft voi n_fft=512
    return np.clip(np.floor((n_bins - 1) * hz / (sr / 2.0)).astype(int), 0, n_bins - 1)


def _mfcc_mean(audio, sr=16000, n_mfcc=13):
    """Dac trung giong noi 13 chieu: log-nang-luong theo dai mel, trung binh theo khung.

    THUAN NUMPY - khong dung librosa/numba. Ly do: `librosa.feature.mfcc` treo >180s
    tren may nay, lam moi cau final bi ket (khong bao gio chot duoc cau).
    Thoi gian chay: ~1-3ms cho 2 giay audio.
    """
    a = np.asarray(audio, dtype=np.float32).ravel()
    if a.size == 0:
        return np.zeros(n_mfcc, dtype=np.float32)
    n_fft, hop = 512, 160
    if a.size < n_fft:
        a = np.pad(a, (0, n_fft - a.size))
    frames = 1 + (a.size - n_fft) // hop
    if frames <= 0:
        return np.zeros(n_mfcc, dtype=np.float32)
    # gioi han so khung de khong ton RAM voi doan dai
    if frames > 2000:
        hop = max(hop, (a.size - n_fft) // 2000)
        frames = 1 + (a.size - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(frames)[:, None]
    window = np.hanning(n_fft).astype(np.float32)
    spec = np.fft.rfft(a[idx] * window, axis=1)
    power = (spec.real ** 2 + spec.imag ** 2).astype(np.float32)

    edges = _mel_edges(n_mfcc, sr)
    bands = np.empty((frames, n_mfcc), dtype=np.float32)
    for i in range(n_mfcc):
        lo = edges[i]
        hi = max(lo + 1, edges[i + 1])
        bands[:, i] = power[:, lo:hi].mean(axis=1)
    return np.log(bands + 1e-8).mean(axis=0).astype(np.float32)


def _shape(v):
    """Chuan hoa vector dac trung -> correlation (tru trung binh + chuan hoa L2).

    Tru trung binh giup phan biet 'chat giong' tot hon la cosine thuong
    (MFCC deu duong nen cosine giua 2 nguoi khac nhau van rat cao).
    """
    v = np.asarray(v, dtype=np.float64).ravel()
    v = v - v.mean()
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


class SpeakerTracker:
    """Gan nhan nguoi noi ON DINH trong 1 phien."""

    def __init__(self, max_k=4, threshold=None, min_sec=0.35, sr=16000):
        if threshold is None:
            try:
                threshold = float(os.getenv("SPEAKER_THRESHOLD", "0.60"))
            except Exception:
                threshold = 0.60
        self.max_k = max(1, int(max_k))
        self.threshold = float(threshold)
        self.min_sec = float(min_sec)
        self.sr = sr
        self.centroids = []   # list[np.ndarray] da _shape()
        self.counts = []      # so cau da gan cho tung nguoi

    @property
    def n_speakers(self) -> int:
        return max(1, len(self.centroids))

    def assign(self, audio):
        """Tra ve (label 0-based, n_speakers). Audio qua ngan -> tra nhan cuoi cung."""
        if audio is None or len(audio) < int(self.sr * self.min_sec):
            return (len(self.centroids) - 1 if self.centroids else 0), self.n_speakers
        try:
            v = _shape(_mfcc_mean(audio, self.sr))
        except Exception:
            return (len(self.centroids) - 1 if self.centroids else 0), self.n_speakers

        if not self.centroids:
            self.centroids.append(v)
            self.counts.append(1)
            return 0, 1

        sims = [float(np.dot(v, c)) for c in self.centroids]
        best = int(np.argmax(sims))
        if sims[best] >= self.threshold or len(self.centroids) >= self.max_k:
            c = self.centroids[best] * self.counts[best] + v
            self.centroids[best] = _shape(c)
            self.counts[best] += 1
            return best, self.n_speakers

        self.centroids.append(v)
        self.counts.append(1)
        return len(self.centroids) - 1, self.n_speakers

    def label(self, audio) -> str:
        i, _ = self.assign(audio)
        return f"Speaker {i + 1}"


# --------------------------------------------------------------------------
# Duong OFFLINE cho file dai (khong can on dinh tung cau): KMeans + silhouette
# --------------------------------------------------------------------------
def estimate_n_speakers(feats, max_k=4):
    """Tu dem so nguoi noi (silhouette). Tra ve k trong 1..max_k."""
    n = len(feats)
    if n <= 1:
        return 1
    try:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        X = np.stack([np.asarray(f, dtype=np.float64) for f in feats])
        mu, sd = X.mean(0), X.std(0) + 1e-6
        X = (X - mu) / sd
        if n == 2:
            d = float(np.linalg.norm(X[0] - X[1]))
            return 2 if d > 1.0 else 1
        best_k, best_s = 1, 0.45
        for k in range(2, min(max_k, n - 1) + 1):
            lab = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
            if len(set(lab.tolist())) < 2:
                continue
            s = silhouette_score(X, lab)
            if s > best_s:
                best_s, best_k = s, k
        return best_k
    except Exception:
        return 1 if n < 3 else 2


def diarize_segments(segments, sr=16000, n_speakers=2):
    """segments: list np.ndarray audio -> list speaker_id (0..n-1)."""
    if not segments:
        return []
    if len(segments) == 1:
        return [0]
    feats = np.stack([_mfcc_mean(s, sr) for s in segments])
    try:
        from sklearn.cluster import KMeans
        k = max(1, min(int(n_speakers), len(segments)))
        lab = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(feats)
        return [int(x) for x in lab]
    except Exception:
        return [i % max(1, int(n_speakers)) for i in range(len(segments))]


def diarize_auto(feats, max_k=4):
    """Tu dem + gan nhan tu list dac trung MFCC (duong offline)."""
    if not feats:
        return [], 0
    if len(feats) == 1:
        return [0], 1
    k = estimate_n_speakers(feats, max_k)
    try:
        from sklearn.cluster import KMeans
        lab = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(np.stack(feats))
        return [int(x) for x in lab], k
    except Exception:
        return [i % k for i in range(len(feats))], k

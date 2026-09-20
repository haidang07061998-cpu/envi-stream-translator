"""Speaker diarization nhe cho EN -> VI.

Van de cua ban cu: `diarize_auto` fit lai KMeans tren TOAN BO tap dac trung moi khi
co cau moi -> chi so cluster doi giua cac lan goi -> "Speaker 1" va "Speaker 2"
hoan vai cho nhau giua cac cau. Ngoai ra `label_speakers` tao dac trung bang
`np.random.randn` (du lieu GIA) -> nhan speaker ngau nhien.

Gio dung `SpeakerTracker`: so sanh dac trung voi cac centroid da luu, chi tao nhan
moi khi thuc su khac -> nhan ON DINH theo thoi gian. Nguong hieu chinh bang
bien moi truong SPEAKER_THRESHOLD (mac dinh 0.60, correlation tren MFCC da tru trung binh).
"""
import os
import numpy as np


def _mfcc_mean(audio, sr=16000, n_mfcc=13):
    try:
        import librosa
        m = librosa.feature.mfcc(y=np.asarray(audio, dtype=np.float32), sr=sr,
                                 n_mfcc=n_mfcc)
        return m.mean(axis=1)
    except Exception:
        # fallback: nang luong + zero-crossing + chia khung thoi gian
        a = np.asarray(audio, dtype=np.float32)
        v = np.zeros(n_mfcc, dtype=np.float32)
        if len(a) == 0:
            return v
        z = float(np.mean(np.abs(np.diff(np.sign(a))))) if len(a) > 1 else 0.0
        v[0] = float(np.sqrt(np.mean(a * a) + 1e-10))
        v[1] = z
        n = max(1, n_mfcc - 2)
        step = max(1, len(a) // n)
        for i in range(n):
            seg = a[i * step:(i + 1) * step]
            v[2 + i] = float(np.sqrt(np.mean(seg * seg) + 1e-10)) if len(seg) else 0.0
        return v


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

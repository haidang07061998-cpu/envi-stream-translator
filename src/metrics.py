"""Do luong chat luong dich + do tre (dung cho bao cao / khoa luan).

Sua loi ban cu:
- `latency_stats` chi lay mean/percentile cua e2e, khong tach phan cache, khong bao
  ty le dat ngan sach realtime, khong co RTF.
- `compute_wer` docstring noi tra ve WER tung cau nhung chi tra ve 1 so.
"""
import numpy as np


def _norm(s: str) -> str:
    import re
    import string
    s = (s or "").lower()
    s = re.sub(f"[{re.escape(string.punctuation)}]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def compute_wer(hyps, refs):
    """WER tong + WER tung cau (tuong thich jiwer 3.x/4.x)."""
    import jiwer
    refs_n = [_norm(r) for r in refs]
    hyps_n = [_norm(h) for h in hyps]
    out = {"wer": float(jiwer.wer(refs_n, hyps_n))}
    try:
        out["per_sentence"] = [float(jiwer.wer(r, h)) for r, h in zip(refs_n, hyps_n)]
    except Exception:
        out["per_sentence"] = []
    out["n"] = len(refs_n)
    return out


def compute_bleu(hyps, refs):
    """BLEU + chrF tieng Viet (sacrebleu). refs: list str hoac list[list]."""
    import sacrebleu
    if refs and isinstance(refs[0], str):
        refs = [refs]
    bleu = sacrebleu.corpus_bleu(hyps, refs)
    chrf = sacrebleu.corpus_chrf(hyps, refs)
    return {"bleu": float(bleu.score), "chrf": float(chrf.score),
            "bleu_sig": str(bleu), "chrf_sig": str(chrf)}


def _stats(vals):
    if not len(vals):
        return {}
    a = np.asarray(vals, dtype=float)
    return {"mean": float(a.mean()), "p50": float(np.median(a)),
            "p90": float(np.percentile(a, 90)), "max": float(a.max())}


def latency_stats(results, target_sec: float = 2.0):
    """Thong ke do tre tung khau + ty le dat ngan sach realtime + RTF."""
    rows = [r for r in results if r.get("en")]
    if not rows:
        return {}
    e2e = [float(r.get("e2e_ms", 0) or 0) for r in rows]
    asr = [float(r.get("asr_ms", 0) or 0) for r in rows]
    nmt = [float(r.get("nmt_ms", 0) or 0) for r in rows]
    tts = [float(r.get("tts_ms", 0) or 0) for r in rows]
    e = _stats(e2e)
    ok = sum(1 for v in e2e if v / 1000.0 <= target_sec)
    out = {"n": len(rows),
           "mean_ms": e["mean"], "p50_ms": e["p50"], "p90_ms": e["p90"], "max_ms": e["max"],
           "mean_asr": float(np.mean(asr)), "mean_nmt": float(np.mean(nmt)),
           "mean_tts": float(np.mean(tts)),
           "asr": _stats(asr), "nmt": _stats(nmt), "tts": _stats(tts),
           "realtime_ok_ratio": ok / len(e2e),
           "target_sec": target_sec}
    # RTF (real-time factor): tong thoi gian xu ly / thoi luong audio
    dur = sum(max(0.0, float(r.get("end", 0) or 0) - float(r.get("start", 0) or 0))
              for r in rows)
    if dur > 0:
        out["audio_sec"] = dur
        out["rtf"] = (sum(e2e) / 1000.0) / dur
    return out

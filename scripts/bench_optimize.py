"""Do de chon cach toi uu TOC DO (khong phong doan).

Do 4 thu:
1. ASR: vad_filter bat/tat, va cat khoang lang truoc khi nhan dang
2. NMT: fp32 vs int8 dynamic quantization (torch.quantization.quantize_dynamic)
3. So sanh CHAT LUONG ban dich giua fp32 va int8 (khong duoc nhanh ma sai)
4. torch.inference_mode vs no_grad

Chay: python scripts/bench_optimize.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(ROOT, "out", "e2e_en.mp3")

SENTS = [
    "We need to check the budget.",
    "The latency is too high for mobile clients.",
    "You should check the API latency before we deploy to production.",
]


def log(m):
    print(m, flush=True)


def trim_silence(a, sr=16000, frame=480, thresh=0.006, pad=0.1):
    """Cat khoang lang dau/cuoi -> bot audio phai chay ASR."""
    if a is None or len(a) < frame * 2:
        return a
    n = len(a) // frame
    rms = np.array([float(np.sqrt((a[i * frame:(i + 1) * frame] ** 2).mean() + 1e-12))
                    for i in range(n)])
    idx = np.where(rms >= thresh)[0]
    if len(idx) == 0:
        return a
    p = int(pad * sr)
    s = max(0, idx[0] * frame - p)
    e = min(len(a), (idx[-1] + 1) * frame + p)
    return a[s:e]


def bench_asr():
    log("\n=== ASR (tiny.en int8, CPU) ===")
    from src.asr import FasterWhisperASR
    from src.audio_utils import load_audio_16k
    asr = FasterWhisperASR("tiny.en", "cpu", "int8", 1, "en", gate_rms=0.0)
    audio = load_audio_16k(AUDIO)
    log(f"audio: {len(audio)/16000:.1f}s")
    trimmed = trim_silence(audio)
    log(f"audio sau khi cat lang: {len(trimmed)/16000:.1f}s")

    for label, a, vad in (("vad=ON  (ca file)", audio, True),
                          ("vad=OFF (ca file)", audio, False),
                          ("vad=OFF (da cat lang)", trimmed, False),
                          ("vad=ON  (da cat lang)", trimmed, True)):
        t0 = time.time()
        r = asr.transcribe(a, 16000, None, vad)
        log(f"  {label:24s} {time.time()-t0:6.2f}s | asr_ms={r['asr_ms']:7.0f} | {r['text'][:60]!r}")


def bench_nmt():
    log("\n=== NMT (VinAI en2vi-v2, CPU) ===")
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    path = "models/vinai-translate-en2vi-v2"
    tok = AutoTokenizer.from_pretrained(path, src_lang="en_XX")
    t0 = time.time()
    model = AutoModelForSeq2SeqLM.from_pretrained(path).eval()
    log(f"  tai fp32: {time.time()-t0:.1f}s")
    vi_id = tok.lang_code_to_id["vi_VN"]
    threads = max(1, min(os.cpu_count() or 4, 8))
    torch.set_num_threads(threads)
    log(f"  torch threads = {threads}")

    def run(m, s, mode="no_grad"):
        ids = tok(s, return_tensors="pt", truncation=True, max_length=128).input_ids
        t0 = time.time()
        ctx = torch.inference_mode() if mode == "inference" else torch.no_grad()
        with ctx:
            out = m.generate(ids, decoder_start_token_id=vi_id, num_beams=1,
                             max_new_tokens=80, no_repeat_ngram_size=3,
                             length_penalty=1.0)
        ms = (time.time() - t0) * 1000
        return tok.batch_decode(out, skip_special_tokens=True)[0].strip(), ms

    log("\n  -- fp32 --")
    base = {}
    for s in SENTS:
        vi, ms = run(model, s)
        base[s] = vi
        log(f"    {ms:7.0f}ms | {vi}")

    log("\n  -- fp32 + inference_mode --")
    for s in SENTS[:1]:
        vi, ms = run(model, s, "inference")
        log(f"    {ms:7.0f}ms | {vi}")

    log("\n  -- int8 dynamic quantization --")
    t0 = time.time()
    qmodel = torch.quantization.quantize_dynamic(
        model, {torch.nn.Linear}, dtype=torch.qint8)
    qmodel.eval()
    log(f"    luong tu hoa xong sau {time.time()-t0:.1f}s")
    same = 0
    for s in SENTS:
        vi, ms = run(qmodel, s)
        ok = (vi == base[s])
        same += ok
        log(f"    {ms:7.0f}ms | giong fp32: {ok} | {vi}")
    log(f"\n  KET LUAN: int8 giong fp32 o {same}/{len(SENTS)} cau")


if __name__ == "__main__":
    log("BENCHMARK TOI UU TOC DO (may nay dang chay server nen so do la bao thu)")
    try:
        bench_asr()
    except Exception as e:
        log(f"ASR bench loi: {type(e).__name__}: {e}")
    try:
        bench_nmt()
    except Exception as e:
        log(f"NMT bench loi: {type(e).__name__}: {e}")
    log("\nXONG")

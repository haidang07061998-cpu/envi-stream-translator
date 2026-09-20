# -*- coding: utf-8 -*-
"""SCRIPT TEST TREN KAGGLE (copy tung cell vao Kaggle Notebook, bat GPU T4 + Internet ON).
Cell 1: cai dat | Cell 2: chay pipeline | Cell 3: danh gia.
Ban local: python kaggle_test.py --audio <file.wav> [--ref_en ... --ref_vi ...]
"""
# ===== CELL 1 (Kaggle): cai dat =====
# !pip install -q faster-whisper transformers accelerate datasets peft sentencepiece edge-tts librosa soundfile jiwer sacrebleu gradio
# !git clone https://github.com/<ban>/envi-stream-translator.git  # hoac upload folder nay len Kaggle Dataset
# import sys; sys.path.insert(0, "envi-stream-translator")

# ===== CELL 2 (Kaggle): chay pipeline tren file audio =====
SAMPLES = [
    # (audio_path, ref_en, ref_vi) - dien duong dan /kaggle/input/... cua ban
    # ("/kaggle/input/ted-test/hello.wav", "hello good morning", "xin chao buoi sang tot lanh"),
]
BASE_ASR = "large-v3-turbo"
BASE_NMT = "vinai/vinai-translate-en2vi-v2"

def kaggle_run(audio_path, save_prefix="/kaggle/working/out"):
    import sys
    sys.path.insert(0, ".")
    from src.asr import FasterWhisperASR
    from src.nmt import NMTTranslator
    from src.tts import EdgeTTSWrapper
    from src.pipeline import CascadedPipeline
    from src.metrics import latency_stats
    import torch
    print("CUDA:", torch.cuda.is_available())
    asr = FasterWhisperASR(BASE_ASR)
    nmt = NMTTranslator(BASE_NMT)
    tts = EdgeTTSWrapper()
    pipe = CascadedPipeline(asr, nmt, tts)
    res = pipe.process_file(audio_path, save_tts_prefix=save_prefix)
    for r in res:
        print(f"[{r.get('start',0):.1f}-{r.get('end',0):.1f}s] EN={r.get('en')!r} | VI={r.get('vi')!r} | "
              f"asr={r.get('asr_ms',0):.0f} nmt={r.get('nmt_ms',0):.0f} tts={r.get('tts_ms',0):.0f} e2e={r.get('e2e_ms',0):.0f}ms")
    print(latency_stats(res))
    return res

# ===== CELL 3 (Kaggle): danh gia WER/BLEU neu co reference =====
def kaggle_eval(results_list):
    """results_list: [(hyp_en, ref_en, hyp_vi, ref_vi), ...] gop tu nhieu file."""
    from src.metrics import compute_wer, compute_bleu
    he = [h for h, _, _, _ in results_list]; re = [r for _, r, _, _ in results_list]
    hv = [h for _, _, h, _ in results_list]; rv = [r for _, _, _, r in results_list]
    print("ASR:", compute_wer(he, re))
    print("NMT:", compute_bleu(hv, rv))

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--ref_en", default="")
    ap.add_argument("--ref_vi", default="")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    res = kaggle_run(a.audio, a.out)
    if a.ref_en or a.ref_vi:
        hy_en = " ".join(r["en"] for r in res if r.get("en"))
        hy_vi = " ".join(r["vi"] for r in res if r.get("en"))
        kaggle_eval([(hy_en, a.ref_en or hy_en, hy_vi, a.ref_vi or hy_vi)])

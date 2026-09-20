"""Test offline local: tao 2 file wav tieng Anh bang Edge-TTS (neu co mang),
roi chay full pipeline ASR->NMT->TTS, in WER/BLEU/latency.
Chay: python test_offline.py"""
import os

OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

CASES = [
    ("hello", "Hello, good morning. Welcome to the international conference.", "Xin chào buổi sáng. Chào mừng bạn đến với hội nghị quốc tế."),
    ("lecture", "The artificial intelligence system translates English speech into Vietnamese in real time.", "Hệ thống trí tuệ nhân tạo dịch giọng nói tiếng Anh sang tiếng Việt theo thời gian thực."),
]

def make_wavs():
    import asyncio
    try:
        import edge_tts
    except ImportError:
        print("thieu edge-tts -> bo qua tao wav, tu bo wav vao out/");
        return []
    async def one(text, path):
        c = edge_tts.Communicate(text, "en-US-JennyNeural")
        with open(path, "wb") as f:
            async for ch in c.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
    import asyncio as aio
    paths = []
    for name, en, vi in CASES:
        p = os.path.join(OUT, name + ".en.mp3")
        if not os.path.exists(p):
            print("tao", p)
            aio.run(one(en, p))
        paths.append(p)
    return paths

def main():
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    make_wavs()
    from src.asr import FasterWhisperASR
    from src.nmt import NMTTranslator
    from src.tts import EdgeTTSWrapper
    from src.pipeline import CascadedPipeline
    from src.metrics import compute_wer, compute_bleu, latency_stats
    asr = FasterWhisperASR("tiny")  # tiny de test local nhanh, len Kaggle doi large-v3-turbo
    try:
        nmt = NMTTranslator()
    except Exception as e:
        print("khong tai duoc NMT (can mang/HF):", e)
        return
    tts = EdgeTTSWrapper()
    pipe = CascadedPipeline(asr, nmt, tts)
    all_en, all_re, all_vi, all_rv, all_res = [], [], [], [], []
    for (name, ref_en, ref_vi) in CASES:
        p = os.path.join(OUT, name + ".en.mp3")
        if not os.path.exists(p):
            print("thieu", p); continue
        res = pipe.process_file(p, save_tts_prefix=os.path.join(OUT, name + ".vi"))
        all_res += res
        he = " ".join(r["en"] for r in res if r.get("en"))
        hv = " ".join(r["vi"] for r in res if r.get("en"))
        all_en.append(he); all_re.append(ref_en); all_vi.append(hv); all_rv.append(ref_vi)
        print(f"[{name}] EN hyp={he!r} VI hyp={hv!r}")
    if all_en:
        print("WER:", compute_wer(all_en, all_re))
        try:
            print("BLEU:", compute_bleu(all_vi, all_rv))
        except Exception as e:
            print("loi sacrebleu:", e)
        print("LATENCY:", latency_stats(all_res))

if __name__ == "__main__":
    main()

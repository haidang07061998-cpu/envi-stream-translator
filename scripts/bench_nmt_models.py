"""So sanh model NMT ve TOC DO va CHAT LUONG (de chon che do nhanh cho CPU yeu).

Chay: python scripts/bench_nmt_models.py
Can mang LAN DAU (tai model nho). Sau do chay offline duoc.

Mac dinh so:
  - vinai/vinai-translate-en2vi-v2 (448M)  : chat luong cao, CHAM tren CPU
  - Helsinki-NLP/opus-mt-en-vi     (77M)   : nho hon ~6x -> nhanh hon nhieu
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SENTS = [
    "We need to check the budget.",
    "The latency is too high for mobile clients.",
    "You should check the API latency before we deploy to production.",
    "Thank you all for joining the meeting today.",
]

MODELS = [
    ("VinAI en2vi-v2 (448M)", "vinai/vinai-translate-en2vi-v2", "en_XX", "vi_VN"),
    ("opus-mt-en-vi (77M)", "Helsinki-NLP/opus-mt-en-vi", "en", "vi"),
]


def log(m):
    print(m, flush=True)


def main():
    from src.nmt import NMTTranslator

    results = {}
    for label, mid, src, tgt in MODELS:
        log(f"\n=== {label} : {mid} ===")
        try:
            t0 = time.time()
            n = NMTTranslator(mid, src, tgt, num_beams=1, max_len=96,
                              accurate_beams=1, ct2_path="models/khong-co")
            load = time.time() - t0
            log(f"  tai xong {load:.1f}s | engine={n.engine}")
            out = []
            times = []
            for s in SENTS:
                t0 = time.time()
                vi, ms = n.translate(s, accurate=False)
                dt = (time.time() - t0) * 1000
                times.append(dt)
                out.append(vi)
                log(f"  {dt:7.0f}ms | {s[:42]:44s} -> {vi}")
            results[label] = (sum(times) / len(times), out)
        except Exception as e:
            log(f"  LOI: {type(e).__name__}: {e}")
            results[label] = (None, None)

    log("\n=== TONG KET ===")
    for label, (avg, out) in results.items():
        if avg:
            log(f"  {label:26s} trung binh {avg:7.0f} ms/cau")
    labels = [l for l, (a, _) in results.items() if a]
    if len(labels) == 2:
        a, b = results[labels[0]][0], results[labels[1]][0]
        log(f"  => {labels[1]} nhanh hon {a / b:.1f}x")
        log("\n  SO SANH BAN DICH:")
        for i, s in enumerate(SENTS):
            log(f"    EN: {s}")
            log(f"      {labels[0]:26s}: {results[labels[0]][1][i]}")
            log(f"      {labels[1]:26s}: {results[labels[1]][1][i]}")


if __name__ == "__main__":
    main()

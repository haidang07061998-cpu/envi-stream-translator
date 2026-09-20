"""Vat them toc do MIEN PHI tu CPU dang co: so luong thread + dich theo batch.

Chay: python scripts/bench_threads_batch.py
Khong can GPU, khong can mang (model da co trong models/).

Do 2 thu:
1. torch.set_num_threads(N) voi N = 4, 6, 8, 10, 12  -> chon N tot nhat
2. Dich tung manh (tuan tu) vs gop 1 batch -> do lai hieu qua
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

SHORT = [
    "We need to check the budget before Friday.",
    "The latency is too high for mobile clients.",
    "Thank you all for joining the meeting today.",
]
LONG = ("You should check the API latency before we deploy to production. "
        "The machine learning pipeline streams audio to the translation model. "
        "Please send me the report by the end of the day.")


def log(m):
    print(m, flush=True)


def main():
    import torch
    from src.nmt import NMTTranslator, split_sentences_en
    from src.config import DEFAULT

    log(f"CPU logic: {os.cpu_count()} | torch mac dinh: {torch.get_num_threads()} threads")
    n = NMTTranslator(DEFAULT.nmt_model, DEFAULT.nmt_src, DEFAULT.nmt_tgt,
                      num_beams=1, max_len=96, accurate_beams=1,
                      ct2_path=DEFAULT.ct2_dir)
    log(f"engine={n.engine} | load xong\n")

    # ---------------- 1) quet so luong thread ----------------
    log("=== 1) Quet torch.set_num_threads ===")
    best = (None, 1e9)
    for th in (4, 6, 8, 10, 12):
        try:
            torch.set_num_threads(th)
        except Exception as e:
            log(f"  {th:2d} threads: khong dat duoc ({e})")
            continue
        # bo qua lan chay dau (warm) roi do lan 2
        for s in SHORT:
            n.translate(s, accurate=False)
        t0 = time.time()
        for s in SHORT:
            n.translate(s + " ", accurate=False)      # them space -> khac cache
        dt = (time.time() - t0) / len(SHORT) * 1000
        log(f"  {th:2d} threads: {dt:7.0f} ms/cau")
        if dt < best[1]:
            best = (th, dt)
    log(f"  => tot nhat: {best[0]} threads ({best[1]:.0f} ms/cau)")
    torch.set_num_threads(best[0] or 8)

    # ---------------- 2) tuan tu vs batch ----------------
    log("\n=== 2) Cau dai: dich tung manh vs gop batch ===")
    parts = split_sentences_en(LONG)
    log(f"  cau dai tach thanh {len(parts)} manh")

    n._cache.clear()
    n._cache_order.clear()
    t0 = time.time()
    seq = [n._translate_one(p, 1) for p in parts]
    t_seq = (time.time() - t0) * 1000

    n._cache.clear()
    n._cache_order.clear()
    t0 = time.time()
    bat = n._hf_vinai_batch(parts, 1)
    t_bat = (time.time() - t0) * 1000

    log(f"  tuan tu: {t_seq:7.0f} ms")
    log(f"  batch  : {t_bat:7.0f} ms  => nhanh hon {t_seq/max(t_bat,1):.2f}x")
    same = sum(1 for a, b in zip(seq, bat) if a.strip() == b.strip())
    log(f"  ket qua giong nhau: {same}/{len(parts)} manh")
    for p, a, b in zip(parts, seq, bat):
        if a.strip() != b.strip():
            log(f"    KHAC: {p}\n      tuan tu: {a}\n      batch  : {b}")

    log("\nKET LUAN: dat TORCH_THREADS=%d" % (best[0] or 8))


if __name__ == "__main__":
    main()

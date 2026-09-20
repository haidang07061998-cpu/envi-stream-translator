"""So sanh CHAT LUONG + TOC DO cac model dich EN -> VI tren cung 1 bo test.

Chay: python scripts/bench_nmt_quality.py
Can mang LAN DAU (tai model). Sau do chay offline duoc.

Muc dich: tra loi cau hoi "lam sao dich nhanh hon" bang SO DO, khong phai cam tinh.
Dung sacrebleu (da co trong requirements) de tinh BLEU + chrF so voi ban dich tham chieu.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (EN, VI tham chieu) - tron cau ngan/dai, thuat ngu va van phong
CASES = [
    ("We need to check the budget before Friday.",
     "Chúng ta cần kiểm tra ngân sách trước thứ Sáu."),
    ("The latency is too high for mobile clients.",
     "Độ trễ quá cao đối với khách hàng di động."),
    ("You should check the API latency before we deploy to production.",
     "Bạn nên kiểm tra độ trễ API trước khi chúng tôi triển khai lên môi trường sản xuất."),
    ("The machine learning pipeline streams audio to the translation model.",
     "Luồng xử lý học máy truyền âm thanh đến mô hình dịch."),
    ("Thank you all for joining the meeting today.",
     "Cảm ơn tất cả các bạn đã tham gia cuộc họp hôm nay."),
    ("Please send me the report by the end of the day.",
     "Vui lòng gửi cho tôi báo cáo trước cuối ngày."),
    ("We will discuss the deployment plan next week.",
     "Chúng ta sẽ thảo luận về kế hoạch triển khai vào tuần tới."),
    ("The new feature reduces the response time significantly.",
     "Tính năng mới giúp giảm đáng kể thời gian phản hồi."),
]

MODELS = [
    ("VinAI en2vi-v2 (448M)", "vinai/vinai-translate-en2vi-v2", "en_XX", "vi_VN"),
    ("VietAI envit5-translation (T5-base ~220M)", "VietAI/envit5-translation", "en", "vi"),
    ("opus-mt-en-vi (77M)", "Helsinki-NLP/opus-mt-en-vi", "en", "vi"),
]

# BENCH_ONLY=envit5 -> chi do model co ten chua chuoi do (tranh tai lai het)
_only = os.getenv("BENCH_ONLY", "").strip().lower()
if _only:
    MODELS = [m for m in MODELS if _only in m[0].lower() or _only in m[1].lower()]


def log(m):
    print(m, flush=True)


def evaluate(label, mid, src, tgt):
    from src.nmt import NMTTranslator
    from src.metrics import compute_bleu, compute_wer

    log(f"\n=== {label} | {mid} ===")
    try:
        t0 = time.time()
        n = NMTTranslator(mid, src, tgt, num_beams=1, max_len=96,
                          accurate_beams=1, ct2_path="models/khong-co")
        load = time.time() - t0
        log(f"  tai model: {load:.1f}s | engine={n.engine}")
    except Exception as e:
        log(f"  KHONG TAI DUOC: {type(e).__name__}: {e}")
        return None

    hyps, refs, times = [], [], []
    for en, vi_ref in CASES:
        t0 = time.time()
        try:
            vi, _ = n.translate(en, accurate=False)
        except Exception as e:
            log(f"  loi dich: {type(e).__name__}: {e}")
            vi = ""
        times.append((time.time() - t0) * 1000)
        hyps.append(vi)
        refs.append(vi_ref)

    try:
        bleu = compute_bleu(hyps, refs)
        quality = f"BLEU {bleu['bleu']:.1f} | chrF {bleu['chrf']:.1f}"
    except Exception as e:
        quality = f"(khong tinh duoc BLEU: {e})"

    avg = sum(times) / len(times)
    log(f"  TOC DO : trung binh {avg:.0f} ms/cau (nhanh nhat {min(times):.0f}, "
        f"cham nhat {max(times):.0f})")
    log(f"  CHAT LUONG: {quality}")
    log("  BAN DICH TUNG CAU:")
    for (en, ref), hy in zip(CASES, hyps):
        mark = "OK " if hy.strip() == ref.strip() else "   "
        log(f"    {mark}EN : {en}")
        log(f"       MAY: {hy}")
        if mark.strip():
            pass
        else:
            log(f"       REF: {ref}")
    return {"label": label, "avg_ms": avg, "bleu": bleu if 'bleu' in dir() else None,
            "hyps": hyps}


def main():
    log("SO SANH MODEL DICH EN->VI (chat luong + toc do)")
    log(f"{len(CASES)} cau test, may nay khong GPU")
    results = []
    for label, mid, src, tgt in MODELS:
        r = evaluate(label, mid, src, tgt)
        if r:
            results.append(r)

    log("\n" + "=" * 60)
    log("TONG KET")
    log(f"{'Model':30s} {'ms/cau':>8s}  {'BLEU':>6s} {'chrF':>6s}")
    for r in results:
        b = r["bleu"]["bleu"] if r["bleu"] else 0
        c = r["bleu"]["chrf"] if r["bleu"] else 0
        log(f"{r['label']:30s} {r['avg_ms']:8.0f}  {b:6.1f} {c:6.1f}")
    if results:
        best_q = max(results, key=lambda r: (r["bleu"]["bleu"] if r["bleu"] else 0))
        fastest = min(results, key=lambda r: r["avg_ms"])
        log(f"\n  Chat luong tot nhat: {best_q['label']}")
        log(f"  Nhanh nhat         : {fastest['label']}")


if __name__ == "__main__":
    main()

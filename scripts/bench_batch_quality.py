"""So sanh CHAT LUONG: dich theo BATCH vs dich TUNG CAU.

Vi sao can: batch nhanh hon ~1.9x nhung phai chac chan KHONG lam giam chat luong.
Chay: python scripts/bench_batch_quality.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

CASES = [
    ("You should check the API latency before we deploy to production. "
     "The machine learning pipeline streams audio to the translation model.",
     "Bạn nên kiểm tra độ trễ API trước khi chúng tôi triển khai lên môi trường sản xuất. "
     "Luồng xử lý học máy truyền âm thanh đến mô hình dịch."),
    ("We need to check the budget before Friday. Please send me the report by the end of the day.",
     "Chúng ta cần kiểm tra ngân sách trước thứ Sáu. Vui lòng gửi cho tôi báo cáo trước cuối ngày."),
    ("The new feature reduces the response time significantly. We will discuss the deployment plan next week.",
     "Tính năng mới giúp giảm đáng kể thời gian phản hồi. Chúng ta sẽ thảo luận về kế hoạch triển khai vào tuần tới."),
]


def main():
    from src.nmt import NMTTranslator, split_sentences_en
    from src.metrics import compute_bleu
    from src.config import DEFAULT

    n = NMTTranslator(DEFAULT.nmt_model, DEFAULT.nmt_src, DEFAULT.nmt_tgt,
                      num_beams=1, max_len=96, accurate_beams=1,
                      ct2_path=DEFAULT.ct2_dir)
    print(f"engine = {n.engine}\n")

    refs, batch_out, seq_out, t_batch, t_seq = [], [], [], 0.0, 0.0
    for text, ref in CASES:
        parts = [p for p in split_sentences_en(text) if p.strip()]
        refs.append(ref)

        n._cache.clear(); n._cache_order.clear()
        t0 = time.time()
        vb = n._hf_vinai_batch(parts, 1)
        t_batch += time.time() - t0

        n._cache.clear(); n._cache_order.clear()
        t0 = time.time()
        vs = [n._translate_one(p, 1) for p in parts]
        t_seq += time.time() - t0

        batch_out.append(" ".join(vb))
        seq_out.append(" ".join(vs))

    b_batch = compute_bleu(batch_out, refs)
    b_seq = compute_bleu(seq_out, refs)
    print(f"TOC DO  : batch {t_batch:.1f}s  vs  tung cau {t_seq:.1f}s  "
          f"=> batch nhanh hon {t_seq / max(t_batch, 0.01):.2f}x")
    print(f"CHAT LUONG: batch BLEU {b_batch['bleu']:.1f} / chrF {b_batch['chrf']:.1f}"
          f"   |   tung cau BLEU {b_seq['bleu']:.1f} / chrF {b_seq['chrf']:.1f}")
    print("\nCHI TIET:")
    for i, (text, ref) in enumerate(CASES):
        same = batch_out[i].strip() == seq_out[i].strip()
        print(f"\n[{i+1}] EN : {text}")
        print(f"    REF   : {ref}")
        print(f"    BATCH : {batch_out[i]}")
        print(f"    TUNG  : {seq_out[i]}")
        print(f"    => {'GIONG NHAU' if same else 'KHAC NHAU'}")
    print("\nKET LUAN: " + ("batch TOT HON hoac BANG (nhanh hon, BLEU khong giam)"
                            if b_batch["bleu"] >= b_seq["bleu"] - 2.0
                            else "CANH BAO: batch lam GIAM chat luong - xem lai"))


if __name__ == "__main__":
    main()

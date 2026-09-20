"""Xuat VinAI en2vi-v2 sang ONNX Runtime va do toc do tren CPU.

Chay: python scripts/bench_onnx.py
Can: pip install onnxruntime "optimum[onnxruntime]"

Vi sao thu ONNX: PyTorch tren CPU con cham; ONNX Runtime thuong nhanh hon 1.5-2.5x
voi transformer decoder ma KHONG doi chat luong (ban fp32), va ban int8 cua ORT dung
quantization chuan (tot hon nhieu so voi torch.quantization.quantize_dynamic da bi
loai vi cut duoi cau).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PATH = "models/vinai-translate-en2vi-v2"
OUT = "models/onnx-vinai-en2vi"
OUT_Q = "models/onnx-vinai-en2vi-int8"

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


def log(m):
    print(m, flush=True)


def score(hyps):
    from src.metrics import compute_bleu
    refs = [r for _, r in CASES]
    try:
        b = compute_bleu(hyps, refs)
        return b["bleu"], b["chrf"]
    except Exception as e:
        log(f"  (khong tinh duoc BLEU: {e})")
        return 0.0, 0.0


def main():
    from transformers import AutoTokenizer
    import torch

    tok = AutoTokenizer.from_pretrained(PATH, src_lang="en_XX")
    vi_id = tok.lang_code_to_id["vi_VN"]

    # ---------------- 1) PyTorch (baseline) ----------------
    log("=== [1/4] PyTorch fp32 (baseline) ===")
    from src.nmt import NMTTranslator
    t0 = time.time()
    n = NMTTranslator(PATH, "en_XX", "vi_VN", num_beams=1, max_len=96,
                      accurate_beams=1, ct2_path="models/khong-co")
    log(f"  tai model {time.time()-t0:.1f}s")
    pt_times, pt_out = [], []
    for en, _ in CASES:
        t0 = time.time()
        vi, _ = n.translate(en, accurate=False)
        pt_times.append((time.time() - t0) * 1000)
        pt_out.append(vi)
    pt_avg = sum(pt_times) / len(pt_times)
    pt_bleu, pt_chrf = score(pt_out)
    log(f"  TOC DO {pt_avg:.0f} ms/cau | BLEU {pt_bleu:.1f} | chrF {pt_chrf:.1f}")
    del n
    import gc
    gc.collect()

    # ---------------- 2) Xuat ONNX ----------------
    log("\n=== [2/4] Xuat sang ONNX (optimum) ===")
    from optimum.onnxruntime import ORTModelForSeq2SeqLM
    if not (os.path.isdir(OUT) and os.listdir(OUT)):
        t0 = time.time()
        try:
            om = ORTModelForSeq2SeqLM.from_pretrained(PATH, export=True, use_cache=True)
            om.save_pretrained(OUT)
            tok.save_pretrained(OUT)
            log(f"  xuat xong {time.time()-t0:.1f}s -> {OUT}")
            del om
            gc.collect()
        except Exception as e:
            log(f"  XUAT THAT BAI: {type(e).__name__}: {e}")
            return
    else:
        log(f"  da co {OUT}")

    # ---------------- 3) ONNX fp32 ----------------
    log("\n=== [3/4] ONNX Runtime fp32 ===")
    t0 = time.time()
    om = ORTModelForSeq2SeqLM.from_pretrained(OUT, use_cache=True)
    log(f"  tai model {time.time()-t0:.1f}s")

    def ort_gen(model, en):
        ids = tok(en, return_tensors="pt", truncation=True, max_length=128)
        out = model.generate(input_ids=ids["input_ids"],
                             attention_mask=ids["attention_mask"],
                             decoder_start_token_id=vi_id, num_beams=1,
                             max_new_tokens=80, no_repeat_ngram_size=3,
                             length_penalty=1.0)
        return tok.batch_decode(out, skip_special_tokens=True)[0].strip()

    ort_times, ort_out = [], []
    for en, _ in CASES:
        t0 = time.time()
        ort_out.append(ort_gen(om, en))
        ort_times.append((time.time() - t0) * 1000)
    ort_avg = sum(ort_times) / len(ort_times)
    ort_bleu, ort_chrf = score(ort_out)
    same = sum(1 for a, b in zip(pt_out, ort_out) if a.strip() == b.strip())
    log(f"  TOC DO {ort_avg:.0f} ms/cau | BLEU {ort_bleu:.1f} | chrF {ort_chrf:.1f}")
    log(f"  GIONG PyTorch: {same}/{len(CASES)} cau")
    log(f"  => nhanh hon {pt_avg/ort_avg:.2f}x")

    # ---------------- 4) ONNX int8 ----------------
    log("\n=== [4/4] ONNX Runtime int8 (dynamic quantization cua ORT) ===")
    try:
        from optimum.onnxruntime import ORTQuantizer
        from optimum.onnxruntime.configuration import AutoQuantizationConfig
        if not (os.path.isdir(OUT_Q) and os.listdir(OUT_Q)):
            q = ORTQuantizer.from_pretrained(OUT)
            try:
                cfg = AutoQuantizationConfig.avx512_vnni(is_static=False, per_channel=False)
            except Exception:
                cfg = AutoQuantizationConfig.avx2(is_static=False, per_channel=False)
            t0 = time.time()
            q.quantize(save_dir=OUT_Q, quantization_config=cfg)
            log(f"  luong tu hoa xong {time.time()-t0:.1f}s -> {OUT_Q}")
        oq = ORTModelForSeq2SeqLM.from_pretrained(OUT_Q, use_cache=True)
        q_times, q_out = [], []
        for en, _ in CASES:
            t0 = time.time()
            q_out.append(ort_gen(oq, en))
            q_times.append((time.time() - t0) * 1000)
        q_avg = sum(q_times) / len(q_times)
        q_bleu, q_chrf = score(q_out)
        qsame = sum(1 for a, b in zip(pt_out, q_out) if a.strip() == b.strip())
        log(f"  TOC DO {q_avg:.0f} ms/cau | BLEU {q_bleu:.1f} | chrF {q_chrf:.1f}")
        log(f"  GIONG PyTorch: {qsame}/{len(CASES)} cau | nhanh hon {pt_avg/q_avg:.2f}x")
        for (en, _), a, b in zip(CASES, pt_out, q_out):
            if a.strip() != b.strip():
                log(f"    KHAC: {en}\n      PT : {a}\n      INT8: {b}")
    except Exception as e:
        log(f"  int8 loi: {type(e).__name__}: {e}")

    log("\n=== TONG KET ===")
    log(f"  PyTorch fp32 : {pt_avg:7.0f} ms/cau | BLEU {pt_bleu:.1f}")
    log(f"  ONNX fp32    : {ort_avg:7.0f} ms/cau | BLEU {ort_bleu:.1f}")


if __name__ == "__main__":
    main()

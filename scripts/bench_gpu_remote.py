"""Do toc do + chat luong cua may GPU THUE (Kaggle / Colab / Modal) tu xa.

Chay:
    python scripts/bench_gpu_remote.py --url https://<ten>.trycloudflare.com
    python scripts/bench_gpu_remote.py            # dung bien NMT_REMOTE_URL

Script goi POST /translate tren may GPU va do:
  - server_ms : thoi gian MAY GPU dich (khong tinh mang)
  - wall_ms   : thoi gian thuc te tu may ban (co tinh mang + tunnel)
  - BLEU/chrF : so voi ban dich tham chieu -> biet GPU co lam mat chat luong khong

Dung de tra loi cau hoi "thue GPU co dang khong" bang SO DO, va de dua vao bao cao.
"""
import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Cung bo test voi scripts/bench_nmt_quality.py de so sanh duoc CPU vs GPU
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

# So sanh tham khao: so do tren may CPU 12 nhan (xem README muc 9)
CPU_REF = {"cpu_contended_ms": 2857, "cpu_clean_ms": 1125}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("NMT_REMOTE_URL", ""),
                    help="dia chi may GPU (vd https://abc.trycloudflare.com)")
    ap.add_argument("--accurate", action="store_true",
                    help="dung beam cao (che do final) thay vi beam=1")
    ap.add_argument("--repeat", type=int, default=1, help="so lan lap moi cau")
    args = ap.parse_args()

    url = (args.url or "").strip().rstrip("/")
    if not url:
        print("Thieu --url (hoac dat bien NMT_REMOTE_URL).")
        sys.exit(1)

    import requests

    print(f"May GPU: {url}")
    try:
        h = requests.get(f"{url}/health", timeout=20).json()
        print(f"  loaded={h.get('loaded')} | asr={h.get('asr')}")
        nmt = h.get("nmt") or {}
        print(f"  NMT engine={nmt.get('engine')} | device={nmt.get('device')} | "
              f"final_beams={nmt.get('final_beams')}")
        if nmt.get("device") != "cuda":
            print("  [!!] CHUA dung GPU (device != cuda). Kiem tra Accelerator da bat chua.")
    except Exception as e:
        print(f"  [!!] khong goi duoc /health: {type(e).__name__}: {e}")
        print("  Kiem tra: cell Kaggle con chay khong? URL con dung khong?")
        sys.exit(1)

    # lam nong (lan goi dau tien cham hon do khoi tao)
    try:
        requests.post(f"{url}/translate", json={"text": "warm up"}, timeout=60)
    except Exception:
        pass

    rows, hyps, refs, server_ms, wall_ms = [], [], [], [], []
    for _ in range(max(1, args.repeat)):
        for en, ref in CASES:
            t0 = time.time()
            r = requests.post(f"{url}/translate",
                              json={"text": en, "accurate": bool(args.accurate)},
                              timeout=90)
            wall = (time.time() - t0) * 1000
            j = r.json()
            rows.append((en, j.get("vi", ""), float(j.get("ms", 0)), wall))
            hyps.append(j.get("vi", ""))
            refs.append(ref)
            server_ms.append(float(j.get("ms", 0)))
            wall_ms.append(wall)

    try:
        from src.metrics import compute_bleu
        b = compute_bleu(hyps, refs)
        quality = f"BLEU {b['bleu']:.1f} | chrF {b['chrf']:.1f}"
    except Exception as e:
        quality = f"(khong tinh duoc BLEU: {e})"

    print(f"\n=== KET QUA ({len(rows)} lan goi) ===")
    print(f"  MAY GPU dich  : trung binh {statistics.mean(server_ms):.0f} ms/cau "
          f"(min {min(server_ms):.0f}, max {max(server_ms):.0f})")
    print(f"  Tu may ban    : trung binh {statistics.mean(wall_ms):.0f} ms/cau "
          f"(gom mang + tunnel)")
    print(f"  Chat luong    : {quality}")

    print("\n=== SO SANH CPU vs GPU ===")
    g = statistics.mean(server_ms)
    for label, cpu in (("CPU (dang chay server)", CPU_REF["cpu_contended_ms"]),
                       ("CPU (may ranh)", CPU_REF["cpu_clean_ms"])):
        print(f"  {label:22s} {cpu:5d} ms/cau  ->  GPU nhanh hon {cpu / g:4.1f}x")

    print("\n=== BAN DICH ===")
    for en, vi, ms, wall in rows[:len(CASES)]:
        print(f"  [{ms:6.0f} ms] {en}")
        print(f"            -> {vi}")

    print("\nGhi chu: 'server_ms' la thoi gian GPU dich that; 'tu may ban' bao gom ca")
    print("vong qua Internet (Cloudflare -> Kaggle), thuong them 200-400ms.")


if __name__ == "__main__":
    main()

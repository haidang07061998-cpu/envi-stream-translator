# Thuê GPU để chạy hệ thống EN→VI — hướng dẫn cho dự án này

Máy hiện tại (CPU 12 nhân, không GPU) cho **~1.1–3.5s/câu** ở khâu dịch. Trên GPU việc này
xuống **~0.15–0.25s/câu** ⇒ đạt realtime thật. Dưới đây là các cách thuê, xếp từ miễn phí tới trả tiền.

---

## 1. Miễn phí trước (ưu tiên cho đồ án)

| Nền tảng | GPU | Giới hạn | Phù hợp với dự án này |
|---|---|---|---|
| **Kaggle** | T4 ×2 hoặc P100, **30 giờ/tuần miễn phí** | Notebook, phiên ~9–12h, không có IP public | **Benchmark + chạy pipeline theo file** (`kaggle_test.py` đã có sẵn cho việc này) |
| **Google Colab Free** | T4 16GB | Phiên ngắn, có thể bị ngắt, không hợp chạy server lâu | Demo nhanh, thử model |
| **Colab Pro** | T4 / V100 / A100 | ~$10/tháng | Demo ổn định hơn |
| **Modal — academic grant** | T4 → H100 | **Tới 10.000 USD credit miễn phí cho sinh viên/nghiên cứu sinh** ([modal.com/pricing](https://modal.com/pricing) → mục *Credit grants for academics*) | **Deploy server thật, trả theo giây** — hợp nhất nếu bạn muốn có URL public cho hội đồng xem |

> Modal cũng tặng **$30 compute miễn phí mỗi tháng** ở gói Starter — đủ cho ~50 giờ GPU T4.

### Chạy trên Kaggle (miễn phí, 30h/tuần)
Trong notebook Kaggle, bật **Accelerator = GPU T4 ×2** rồi:
```python
!pip install -q faster-whisper transformers sentencepiece ctranslate2
!git clone https://github.com/<ban>/envi-stream-translator.git
%cd envi-stream-translator
import sys; sys.path.insert(0, '.')
# chạy pipeline trên file audio có sẵn trong /kaggle/input/...
!python kaggle_test.py --audio /kaggle/input/<dataset>/sample.wav --ref_en "..." --ref_vi "..."
```
Kaggle không mở được port ra Internet, nên dùng nó để **đo tốc độ/độ chính xác**, không để làm server.

---

## 2. Thuê theo giờ (trả theo giây) — giá lấy trực tiếp 20/09/2026

### Modal ([modal.com/pricing](https://modal.com/pricing)) — serverless, trả theo giây
| GPU | USD/giờ | Ghi chú |
|---|---|---|
| **T4 16GB** | **$0.59** | Đủ chạy VinAI fp16 + Whisper turbo |
| L4 24GB | $0.80 | Nhanh hơn T4 ~1.5× |
| A10 24GB | $1.10 | |
| L40S 48GB | $1.95 | |
| A100 40GB | $2.10 | |
| H100 80GB | $3.95 | Không cần cho dự án này |

### Nơi khác (giá thị trường, biến động — tự kiểm tra trước khi thuê)
| Nhà cung cấp | Kiểu | Khoảng giá tham khảo |
|---|---|---|
| **Vast.ai** | Chợ GPU, trả theo giây, có gói *interruptible* rẻ hơn 50%+ | RTX 3090/4090 thường **$0.20–0.45/giờ** |
| **RunPod** | Pod theo giờ + serverless | RTX 4090 ~**$0.34–0.69/giờ** |
| Paperspace / Lambda / TensorDock | Pod theo giờ | Tương tự Vast/RunPod |
| Google Cloud / AWS / Azure | Máy ảo GPU, có **spot** rẻ hơn | T4 spot ~**$0.15–0.35/giờ** (thêm phí lưu trữ/egress) |

---

## 3. Nhà cung cấp Việt Nam (nếu cần hoá đơn VND)

**VNG Cloud · Viettel IDC · FPT Cloud** đều có GPU thuê theo giờ, thanh toán VND, độ trễ tới
người dùng trong nước thấp. Thường **đắt hơn Vast.ai** nhưng tiện về hợp đồng/hoá đơn — phù hợp
nếu nhà trường hoặc doanh nghiệp cần chứng từ.

---

## 4. Deploy dự án này lên GPU thuê

### Cách A — chạy TOÀN BỘ server trên máy GPU (khuyến nghị cho demo/bảo vệ)
```bash
# 1) Trên máy GPU: lấy code (git clone, hoặc scp cả thư mục)
git clone <repo> && cd envi-stream-translator

# 2) Cài đặt: requirements.txt (CPU-safe) + requirements-gpu.txt (torch CUDA)
pip install -r requirements.txt
pip install -r requirements-gpu.txt

# 3) Tải model (1 lần)
python scripts/download_offline_models.py

# 4) Chạy server — GPU sẽ tự chọn model tốt nhất
export ASR_MODEL=large-v3-turbo          # PowerShell: $env:ASR_MODEL='large-v3-turbo'
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000

# 5) Mở URL public không cần IP tĩnh / mở port
cloudflared tunnel --url http://localhost:8000      # hoặc: ngrok http 8000
```
Máy bạn chỉ cần mở URL đó: `/m` để nói, `/room/<sid>` cho người nghe, QR hoạt động bình thường.

### Cách B — chỉ đẩy khâu DỊCH lên GPU (giữ ASR/TTS ở máy)
- Chỉ gửi **text** qua mạng (không gửi audio) ⇒ nhẹ băng thông hơn nhiều
- Thêm 1 network hop (~50–200ms) nhưng vẫn nhanh hơn CPU rất nhiều
- **Phù hợp hơn cho chế độ họp mật**: audio không rời máy, chỉ text
- Cần thêm một endpoint nhỏ trên máy GPU; có thể bổ sung vào repo nếu cần

---

## 5. Hiệu năng kỳ vọng

| Khâu | CPU (máy bạn) | T4 | RTX 4090 |
|---|---|---|---|
| ASR `tiny.en`, câu 3s | ~1.1s | ~0.15s | ~0.05s |
| ASR `large-v3-turbo` | không kịp realtime | ~0.3s | ~0.1s |
| NMT VinAI 448M, beam=1 | **1.1–3.5s** | **~0.15–0.25s** | ~0.06s |
| **Tổng mỗi câu (E2E)** | **~5–9s** | **~0.5–0.8s** | **~0.2–0.3s** |

⇒ Trên T4 đã **đạt realtime (<1s)**. Code đã sẵn sàng cho CUDA, không cần sửa gì:
- `resolve_asr_model(use_cuda=True)` → tự chọn `large-v3-turbo`, compute `int8_float16`
- NMT tự chuyển `.half()` trên GPU, beam final = 4
- `torch.quantization.quantize_dynamic` tự **bỏ qua** khi có GPU (chỉ dùng cho CPU)
- CTranslate2 vẫn mặc định TẮT (đã đo là sinh văn bản lặp vô nghĩa)

Kiểm tra nhanh sau khi lên GPU:
```bash
curl http://localhost:8000/health      # xem "asr" và engine NMT
curl http://localhost:8000/metrics     # p50/p90 thật
```

---

## 6. ⚠️ Cảnh báo riêng tư — đọc trước khi thuê

Thuê GPU nghĩa là **audio/text rời khỏi máy bạn**. Với chế độ **họp mật** (`OFFLINE=1`,
`CONFIDENTIAL=1`) điều đó **phá vỡ cam kết** — đúng lỗi mà Saydi bị chỉ ra: quảng cáo
*"audio stays on your device"* nhưng privacy policy ghi rõ gửi lên Deepgram + Google.

| Mục đích | Nên dùng |
|---|---|
| Demo, bảo vệ đồ án, benchmark, thử model | GPU thuê ✅ |
| Triển khai cho cuộc họp mật thật | **GPU tại chỗ** (mua/thuê on-prem) hoặc giữ **chế độ CPU offline** ✅ |
| Muốn vừa nhanh vừa riêng tư | Cách B (chỉ đẩy text lên GPU) — vẫn là thoả hiệp, phải nói rõ với người dùng cuối |

---

## 7. Chi phí cho một buổi bảo vệ (4 giờ)

| Lựa chọn | Chi phí |
|---|---|
| Kaggle T4 | **0 đồng** (trong 30h/tuần) |
| Modal T4 | 4 × $0.59 = **$2.36** — nhưng có $30 free/tháng ⇒ **0 đồng** |
| Vast.ai RTX 4090 (interruptible) | ~**$1.0–1.8** |
| Modal A100 40GB | 4 × $2.10 = **$8.40** |

**Gợi ý:** bắt đầu bằng **Kaggle** để đo tốc độ/độ chính xác (miễn phí), rồi dùng
**Modal academic grant** nếu cần một URL public cho hội đồng xem trực tiếp.

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

### Chạy trên Kaggle (miễn phí, 30h/tuần) — **đã có sẵn mọi thứ**

Repo đã chuẩn bị 2 file để bạn không phải copy-paste:
- `kaggle_envi_server.ipynb` — notebook import thẳng vào Kaggle
- `dist/envi-stream-translator-kaggle.zip` — gói code 194 KB để upload làm dataset
  (tạo lại bằng lệnh ở mục *Tạo lại gói zip* bên dưới)

**5 bước (khoảng 3 phút):**

| Bước | Thao tác |
|---|---|
| 1 | Kaggle → **Datasets** → **New Dataset** → kéo thả `dist/envi-stream-translator-kaggle.zip` → **Create** |
| 2 | Mở notebook của bạn → panel **Settings** → **Accelerator: GPU T4 ×2**, **Internet: ON** (cần xác minh số điện thoại) |
| 3 | Panel **Data** / **Add Input** → chọn dataset vừa tạo |
| 4 | **File → Import Notebook** → chọn `kaggle_envi_server.ipynb` (hoặc dán nội dung file vào 1 cell) |
| 5 | **Run All** → đợi 3–6 phút → script in ra `https://<tên>.trycloudflare.com` |

Sau đó:
- `<URL>/m` — nói tiếng Anh (mic chạy được vì là `https`)
- `<URL>/room/<sid>` — người nghe / quét QR
- Trên máy bạn, muốn nhẹ RAM: `set NMT_REMOTE_URL=<URL>` rồi chạy `desktop_app_v2.py`

Script tự làm hết: kiểm tra GPU + Internet → cài thư viện thiếu → **tìm code trong dataset
(chỉ đọc) và copy sang `/kaggle/working`** để ghi được model → tải model → chạy server → mở tunnel.

**Tạo lại gói zip** (khi bạn sửa code, chạy lại lệnh này rồi upload lại dataset):
```powershell
python scripts/make_kaggle_zip.py
```
> ⚠️ **ĐỪNG dùng `Compress-Archive` của PowerShell.** Nó ghi tên file trong zip bằng dấu `\`
> (vd `envi-stream-translator\app\server.py`), nhưng chuẩn ZIP yêu cầu `/`, nên Kaggle từ chối:
> *"... contains a forbidden character in name ('\')"*. Script Python ở trên ghi đúng `/`
> và tự kiểm tra lại (in ra `Entry co dau '\' (LOI Kaggle): 0`).

> Kaggle **chỉ trừ giờ GPU khi cell đang chạy** — đóng notebook là không tốn gì.
> Phiên kéo dài ~9–12 giờ; hết thì chạy lại cell 2 là có URL mới.

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

---

## 8. Tính tiền như thế nào — chỗ dễ hiểu sai nhất

**Nguyên tắc chung: tiền chỉ tính khi GPU ĐANG CHẠY. Cài đặt / upload / deploy = 0 đồng.**
Nhưng "đang chạy" định nghĩa khác nhau ở từng nơi — và có một cái bẫy thật.

| Nền tảng | Bắt đầu tính từ lúc nào | Dừng tính khi nào | Có tính lúc rảnh không? |
|---|---|---|---|
| **Kaggle** | Khi bạn **bấm Run** một notebook có bật GPU | Khi bấm **Stop** / đóng phiên / hết phiên | ❌ Không. Chỉ trừ vào **30 giờ/tuần** |
| **Colab** | Khi bật GPU và chạy cell | Khi ngắt phiên; tự ngắt sau ~90 phút rảnh | ❌ Không |
| **Modal** | Khi **có request** đi vào (serverless) | Khi container tắt — **sau `scaledown_window` giây kể từ request cuối** | ⚠️ **CÓ**, trong khoảng `scaledown_window` (mặc định 60s) |
| **Vast.ai / RunPod** | Ngay khi bạn **bật pod** | Chỉ khi bạn **tự Stop/Destroy** | ⚠️ **CÓ, liên tục** — quên tắt là tính tiền cả đêm |
| **Google Cloud / AWS** | Khi VM ở trạng thái running | Khi **stop** (nhưng đĩa vẫn tính tiền) | ⚠️ CÓ khi running; stop rồi vẫn tốn tiền đĩa |

### Modal — con số cụ thể

Modal ghi rõ trong [docs](https://modal.com/docs/guide/cold-start):
> *"Increasing the `scaledown_window` reduces the chance that subsequent requests will require
> a cold start, **although you will be billed for any resources used while the container is
> idle**."*

- `modal deploy` **không** làm phát sinh tiền — chỉ build image 1 lần (rất nhẹ).
- Chỉ khi bạn **gọi** vào (nói một câu → 1 request) thì container mới bật → **bắt đầu tính theo giây**.
- Hết request, container còn "thức" thêm `scaledown_window` giây để lần sau trả lời nhanh
  → **khoảng đó vẫn bị tính tiền**. Mặc định Modal = **60 giây**; cho phép **2s … 20 phút**.
- Trong `modal_app.py` tôi đã để `min_containers=0` ⇒ **không bao giờ** giữ container chạy khi rảnh,
  nên không có chuyện "để đó cả tháng vẫn bị trừ tiền".

**Chi phí T4 ($0.000164/giây):**

| Việc | Thời gian tính tiền | Tiền |
|---|---|---|
| Dịch 1 câu | ~0.2s | ~$0.00003 |
| Một lần tắt máy (idle 60s) | 60s | ~$0.010 (1 xu) |
| Nếu để `MODAL_KEEPWARM=300` | 300s | ~$0.049 (5 xu) |
| **1 buổi demo 2 giờ nói liên tục** | 2 giờ | **~$1.18** |
| **$30 miễn phí/tháng** | — | **~50 giờ T4** |

### Cách tự bảo vệ khỏi hoá đơn bất ngờ

1. **Modal**: đặt `MODAL_KEEPWARM=2` (tắt gần như ngay) và vào
   *Dashboard → Settings → Budgets* đặt **trần chi tiêu**. Hết $30 free là dừng, không tự trừ thêm.
2. **Vast.ai / RunPod**: **luôn bấm Stop/Destroy** sau khi dùng. Đặt nhắc nhở trên điện thoại.
   RunPod còn tính phí **lưu trữ** cho pod đã stop (~$0.10/GB/tháng) → dùng xong thì **Destroy**.
3. **Kaggle/Colab**: không có rủi ro tiền, chỉ hết quota tuần.
4. **Hệ thống này đã tự tiết kiệm**: chế độ GPU từ xa có **cache ở máy** — câu lặp lại
   ("Cảm ơn", "Vâng", thuật ngữ) **không gửi request** lên GPU, nên không tốn tiền cho câu trùng.

### Với chế độ hybrid (`NMT_REMOTE_URL`) thì tính tiền ra sao?

- **Chỉ gửi request khi có câu cần dịch.** Bạn im lặng → không có request → Modal scale to zero → **không tính tiền**.
- Nói liên tục trong 1 giờ → container thức liên tục → tính **đúng 1 giờ GPU**.
- Nói thưa (1 câu mỗi 10 phút) → mỗi câu làm container thức thêm `scaledown_window`
  → nếu để 60s thì mỗi câu tốn ~1 xu, 6 câu/giờ ≈ **$0.06/giờ** — vẫn rẻ, nhưng nếu dùng
  rất thưa thì nên đặt `MODAL_KEEPWARM=2`.

# envi-stream-translator — Dịch giọng nói **Anh → Việt** thời gian thực

Hệ thống nghe tiếng Anh (mic hoặc âm thanh cuộc họp) và hiện **phụ đề EN + bản dịch VI**
gần như tức thời, kèm xuất biên bản và chế độ họp mật offline.

**Phạm vi: CHỈ 1 cặp ngôn ngữ EN → VI.** Không nhận VI→EN, không đa ngôn ngữ.

```
mic / âm thanh hệ thống / tab trình duyệt
        │  PCM 16k int16
        ▼
   ┌─────────┐   ┌──────────────┐   ┌──────────────────┐   ┌───────────┐
   │ VAD +   │──▶│ ASR          │──▶│ NMT              │──▶│ TTS (tuỳ) │
   │ chunking│   │ faster-whisper│   │ VinAI en2vi-v2   │   │ Edge/Piper│
   └─────────┘   │ tiny.en/turbo │   │ + CT2 int8 + từ  │   └───────────┘
                 └──────────────┘   │   điển ngữ cảnh  │
                                    └──────────────────┘
        │                                   │
        │  partial (~0.3-0.5s)              │  final (chốt câu theo GIÂY im lặng)
        ▼                                   ▼
   màn hình 1: sub EN  ──▶  màn hình 2: sub VI  ──▶  TXT / SRT / VTT + tóm tắt
                                                     + phòng QR cho người nghe
```

---

## 1. Chạy nhanh

### A. Server + web (phòng họp, nhiều người nghe)
```powershell
pip install -r requirements.txt
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
```
- Người nói: mở `http://localhost:8000/m` (PWA) → bấm **BẬT MIC**
- Người nghe: mở link `http://<ip>:8000/room/<sid>` hoặc **quét mã QR** trên điện thoại
- Lần đầu chạy sẽ tải model Whisper + VinAI (1–2 phút).

> Mic trong trình duyệt chỉ hoạt động trên `localhost` hoặc **HTTPS**. Điện thoại vào
> qua IP LAN bằng HTTP sẽ bị chặn mic — hãy nói trên máy chủ, điện thoại chỉ để nghe.

### B. Máy họp mật — offline 100%
```powershell
.\run_hop_mat_offline.ps1        # hoặc run_hop_mat_offline.bat
```
Đặt `OFFLINE=1` + `CONFIDENTIAL=1`: chặn mọi call ra cloud (LLM/TTS online), ẩn `/docs`,
PIN phòng, và **xoá file/phòng ngay sau khi xuất**.

### C. App desktop (không cần server, không cần browser)
```powershell
pip install -r requirements-desktop.txt
.\run_desktop_v2.bat             # hoặc python desktop_app_v2.py
```
Chọn nguồn âm thanh: **Micro** hoặc **Âm thanh hệ thống (loopback)** — loopback thu được
tiếng của *mọi* ứng dụng (Zoom/Teams/Meet/YouTube) mà không cần extension.

### D. Extension Chrome (dịch tab Meet / Zoom Web / Teams / Webex)
`chrome://extensions` → bật *Developer mode* → **Load unpacked** → chọn thư mục `extension/`.
Xem `extension/README.md`.

### E. Tăng tốc NMT — đọc kỹ trước khi bật
```powershell
python scripts/download_offline_models.py  # tải sẵn model offline (gồm Piper vi_VN)
python scripts/convert_nmt_ct2.py          # convert CT2 (xem cảnh báo bên dưới)
```
> ⚠️ **CT2 mặc định TẮT — đường "nhanh 4-5x" trong code gốc KHÔNG dùng được.**
> Đo thực tế trên máy này: CT2 của VinAI en2vi-v2 sinh **văn bản lặp vô nghĩa** với nhiều
> câu ngắn — `"We need to check the budget."` → `"Chúng Chúng Chúng chúng Chúng Chúng We Chúng..."`
> — trong khi cùng câu đó qua HF PyTorch cho `"Chúng ta cần kiểm tra ngân sách."`.
> **Đã thử cả `int8_float32` và `float32`: cả hai đều hỏng** ⇒ lỗi nằm ở bước convert mBART
> sang CTranslate2, không phải ở lượng tử hoá. Vì vậy hệ thống **không tự bật CT2**.
> Nếu vẫn muốn thử: `set ENABLE_CT2=1` (có self-test lúc khởi động + guard `looks_degenerate()`
> tự tắt sau 3 lần sinh rác, nên rác không bao giờ tới người dùng).

---

## 2. Tính năng

| Nhóm | Tính năng |
|---|---|
| Dịch trực tiếp | 2 chế độ: `translate` (EN→VI) và `transcribe` (chỉ EN) · partial hiện ngay · final chốt theo thời gian im lặng · chống lặp từ ở biên câu |
| Ngữ cảnh (AI Context Engine) | Scenario Gallery (event/tech/sales/education) · Meeting Details & Keywords (nạp vào `initial_prompt` của Whisper) · Custom Dictionary tối đa 50 thuật ngữ EN=VI |
| Người nói | Tự đếm + gán nhãn `Speaker N` **ổn định** theo centroid (không hoán vai giữa các câu) |
| Phòng & người nghe | Tạo phòng, **QR join**, PIN phòng, WebSocket fan-out realtime, hàng trăm người nghe |
| Biên bản | Tóm tắt + Action items (offline-extractive hoặc LLM nếu có key) · xuất **TXT (EN/VI/cả hai) · SRT · VTT** đúng thời gian thật |
| Riêng tư | `OFFLINE`/`CONFIDENTIAL`: không gọi cloud, PIN hash + so sánh constant-time, xoá file tạm sau khi gửi, phòng tự hết hạn |
| Nền tảng | Server FastAPI · PWA mobile · trang người nghe · app desktop Tkinter · extension Chrome MV3 · Docker (nginx + 3 replica + Redis) |

### So với Saydi AI (tham chiếu)
Dựa trên khảo sát công khai (xem `SAYDI_AI_RESEARCH_REPORT.md`):

| | Saydi | Hệ thống này |
|---|---|---|
| Số ngôn ngữ | 61 | **1 cặp EN→VI** (đúng phạm vi) |
| ASR / MT | Deepgram + Google (cloud) | **Whisper + VinAI en2vi-v2, chạy local** |
| QR join cho khán giả | ✅ | ✅ |
| Dual-pane caption | ✅ | ✅ |
| Glossary 50 thuật ngữ | ✅ | ✅ |
| Xuất TXT/SRT/VTT | ❌ (không tài liệu nào nhắc) | ✅ **SRT/VTT đúng timing** |
| Chế độ offline / họp mật | ❌ (quảng cáo "on-device" nhưng privacy policy ghi rõ dùng Deepgram+Google) | ✅ **offline thật, kiểm chứng được bằng log** |
| PIN phòng | ❌ không có | ✅ |
| Độ trễ | "near-zero"/"1S" (không benchmark) | đo thật: `/metrics` + `latency_stats` (p50/p90/RTF) |

---

## 3. API

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/health` | trạng thái model, chế độ, offline/confidential |
| GET | `/metrics` | số phiên, số caption, p50/p90 ASR·NMT·E2E |
| GET | `/m` · `/room/{sid}` | PWA người nói · trang người nghe |
| POST | `/session/create` | form: `topic, host, pin, mode, scenario, keywords, details, terms` |
| POST | `/session/{sid}/context` | đổi ngữ cảnh/thuật ngữ **giữa cuộc họp** |
| GET | `/session/{sid}/captions?since=N` | PIN qua header `X-Room-Pin` hoặc `?pin=` |
| GET | `/session/{sid}/export` | `format=txt\|srt\|vtt`, `mode=both\|en\|vi` |
| GET | `/session/{sid}/qr.png` | mã QR (cần `qrcode[pil]`) |
| POST | `/session/{sid}/summary` | biên bản + action items |
| DELETE | `/session/{sid}` | xoá ngay (chế độ mật) |
| POST | `/translate_file` · `/doctranslate` · `/summarize` | dịch file audio / docx-txt / tóm tắt |
| WS | `/ws/stream?sid&partial&mode&tts&pin` | client gửi PCM int16 16k; frame rỗng = chốt câu cuối |
| WS | `/ws/room/{sid}?pin` | người nghe nhận `snapshot` + `caption` realtime |

Thông điệp server → client trên `/ws/stream`:
```json
{"kind":"status","status":"loading|ready|error","msg":"..."}
{"kind":"partial","en":"...","vi":null,"asr_ms":120.0,"nmt_ms":0.0,"unstable":true}
{"kind":"final","id":7,"en":"...","vi":"...","speaker":"Speaker 1","n_speakers":2,
 "scenario":"tech","asr_ms":180.0,"nmt_ms":95.0,"tts_ms":0.0,"e2e_ms":275.0,
 "audio_vi":null,"audio_mime":"audio/mp3"}
```

---

## 4. Cấu hình (biến môi trường)

Mọi tham số nằm ở **một chỗ duy nhất**: `src/config.py` (không hardcode trong app).

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `MODE` | `translate` | `translate` (EN→VI) hoặc `transcribe` (chỉ EN) |
| `ASR_MODEL` | — | ép model ASR; nếu không đặt: GPU→`large-v3-turbo`, CPU→`tiny.en` |
| `ASR_MODEL_OFFLINE` | `tiny.en` | model dùng khi chỉ có CPU |
| `ASR_DEVICE` | `auto` | `cuda` / `cpu` (máy thuê GPU có thể ép) |
| `ASR_COMPUTE` | `auto` | `int8_float16` (cuda) / `int8` (cpu); ép `float16` nếu GPU không hỗ trợ int8 |
| `PARTIAL_EVERY` | `0.8` | nhịp hiện chữ trực tiếp (giây) |
| `FINAL_SILENCE` | `0.8` | im lặng bao lâu thì chốt câu |
| `MAX_SEG` | `8.0` | ép chốt câu nếu nói liên tục |
| `OVERLAP_KEEP` | `0.5` | đuôi buffer giữ lại (chống mất chữ biên) |
| `SPEAK_RMS` / `ASR_GATE_RMS` | `0.008` / `0.004` | ngưỡng "đang nói" / ngưỡng bỏ qua ASR |
| `ACCURATE_BEAMS` | auto (GPU 4 / CPU 1) | beam cho câu final |
| `ASR_VAD` | `0` | bật VAD nội bộ của Whisper (tắt nhanh hơn ~15%, kết quả như nhau) |
| `NMT_INT8` | `0` | int8 dynamic quantization — nhanh hơn nhưng **cụt đuôi câu** (đo được) |
| `TORCH_THREADS` | `8` | số CPU cho NMT (máy nhiều nhân có thể tăng; quá cao sẽ tranh CPU với ASR) |
| `FINAL_SILENCE` | `0.8` | giảm xuống `0.5` → chốt câu sớm hơn → bản dịch bắt đầu sớm hơn |
| `MAX_SEG` | `8.0` | giảm xuống `5` → mỗi câu ngắn hơn → phụ đề VI ra đều hơn |
| `PARTIAL_VI` | `0` | dịch cả partial (tốn CPU, làm câu final chậm đi) |
| `ENABLE_CT2` | `0` (**TẮT**) | bật CTranslate2 int8 — chỉ bật sau khi tự kiểm tra chất lượng |
| `DISABLE_CT2` | `0` | tắt cứng CT2 (thắng cả `ENABLE_CT2`) |
| `CT2_EN2VI` / `CT2_QUANT` | `models/ct2-en2vi-v2-int8` / `int8_float32` | thư mục CT2 / kiểu lượng tử hoá khi convert |
| `SPEAKER_THRESHOLD` | `0.60` | ngưỡng tách người nói |
| `TTS_ENGINE` | auto (`edge`/`offline`) | giọng đọc tiếng Việt |
| `OFFLINE` / `CONFIDENTIAL` | `0` | chế độ họp mật, không ra Internet |
| `GLOSSARY_MAX` | `50` | trần Custom Dictionary |
| `MAX_CAPTIONS` | `500` | trần số câu mỗi phòng |
| `SESSION_TTL_HOURS` | `4` | phòng tự hết hạn |
| `REDIS_URL` | — | bật lưu caption bằng Redis LIST + pub/sub (chạy nhiều replica) |
| `SERVER_HOST` | `http://localhost:8000` | host dùng để sinh link/QR |

---

## 5. Test

```powershell
python -m unittest discover -s tests -t .      # 77 test, ~1.1s, KHÔNG cần model/mạng
```
> Lưu ý: nếu máy đang tải model (CPU 100%), một test WebSocket có thể timeout do tranh CPU.
> Đây là giới hạn của môi trường chạy test, không phải lỗi logic — chạy lại khi máy rảnh.
- `tests/test_core.py` — lọc hallucination, chống lặp overlap, context engine, PIN hash,
  SRT/VTT timing, diarization ổn định, config, metrics, summarizer + kiểm tra cú pháp JS của PWA/extension.
- `tests/test_server.py` — tích hợp HTTP/WS thật (TestClient, không tải model): routing,
  phân quyền PIN, export, tóm tắt, fan-out WS, và nhánh từ chối của `/ws/stream`.

Đo tải thật (WS speaker + WS listener):
```powershell
locust -f locustfile.py --host http://localhost --headless -u 20 -r 5 -t 2m
```

---

## 6. Cấu trúc

```
src/
  config.py          # NGUỒN DUY NHẤT cho mọi tham số
  asr.py             # faster-whisper + initial_prompt (bias tên riêng/thuật ngữ)
  nmt.py             # VinAI en2vi-v2, CT2 int8, cache LRU, postprocess thuật ngữ
  simultaneous.py    # partial/final, lọc hallucination, chống lặp overlap, gate năng lượng
  live_session.py    # ghép ASR+NMT+ngữ cảnh+speaker cho 1 phiên
  context_engine.py  # Scenario Gallery + Keywords + Custom Dictionary (50)
  diarization.py     # SpeakerTracker ổn định + KMeans cho file dài
  rooms.py           # phòng, PIN hash, caption, export TXT/SRT/VTT, QR, fan-out
  metrics.py         # WER/BLEU/chrF + latency p50/p90/RTF
  tts.py             # Edge TTS (executor dùng lại + timeout + circuit breaker)
  tts_offline.py     # Piper / SAPI5
app/server.py        # FastAPI: WS, phòng, export, metrics
static/mobile/       # PWA người nói (AudioWorklet, không vòng lặp mic→loa)
static/room/         # trang người nghe (QR, PIN, WS realtime)
extension/           # Chrome MV3: tabCapture → offscreen → WS
desktop_app_v2.py    # app desktop Tkinter (mic hoặc loopback hệ thống)
tests/               # 72 test tự động
scripts/             # tải model offline, convert CT2
```

---

## 7. Đã sửa trong lần nâng cấp này

| # | Lỗi cũ | Hệ quả | Cách sửa |
|---|---|---|---|
| 1 | `static/mobile/index.html` có dấu `\|` lạc trong `<script>` | PWA mobile **chết hoàn toàn** (SyntaxError) | viết lại PWA + test tự động parse JS bằng Node |
| 2 | `_clean_en` dùng `startswith("you ")` | **xoá oan** mọi câu bắt đầu bằng "You ..." | chỉ lọc khớp chính xác / câu lặp từ |
| 3 | Trang `/room/{sid}` không truyền PIN | phòng có PIN **không xem được** | PIN qua header + ô nhập PIN trên cả 2 trang |
| 4 | Chốt câu theo **số chunk** | mobile chốt sau 0.34s, desktop sau 1s | endpointing theo **giây** từ config |
| 5 | ASR/NMT chạy đồng bộ trong coroutine | 1 người nói là **cả server đứng** | đẩy sang threadpool, lock riêng từng model |
| 6 | `push_caption` đọc-sửa-ghi cả JSON blob | **mất caption** khi chạy 3 replica | Redis LIST (`RPUSH`+`LTRIM`) + pub/sub |
| 7 | `export_session_srt` bịa 3s/cue | phụ đề **lệch hoàn toàn** | dùng `t_start`/`t_end` thật |
| 8 | CT2 `target_prefix` truyền **id số** | đường "nhanh 4-5x" **chưa từng chạy** | truyền token string + log lỗi thay vì nuốt |
| 9 | `os.environ.setdefault("ASR_MODEL","tiny.en")` | máy có GPU vẫn chạy model yếu nhất | `resolve_asr_model(use_cuda)` |
| 10 | `finalize_fast` không dedup overlap | **lặp từ** ở đầu mỗi câu | `strip_overlap()` |
| 11 | KMeans fit lại mỗi câu | nhãn `Speaker 1/2` **hoán vai** | `SpeakerTracker` theo centroid |
| 12 | `label_speakers` dùng `np.random.randn` | nhãn người nói **ngẫu nhiên** | xoá code giả |
| 13 | `session_qr` chỉ trả link | "QR share" không có QR | sinh PNG thật (fallback link) |
| 14 | `os.environ.pop` API key giữa request | tắt LLM **vĩnh viễn** cho cả process | chỉ kiểm tra cờ khi gọi |
| 15 | TTS tạo thread mới mỗi câu, không timeout | mạng chậm là **treo phiên** | 1 executor + timeout + circuit breaker |
| 16 | Preset scenario không bao giờ áp dụng | "Scenario Gallery" chỉ để trang trí | `glossary()` gộp preset + custom |
| 17 | Index caption lệch khi vượt 500 câu | bản dịch **ghi nhầm dòng** | dùng `id` ổn định |
| 18 | `/doctranslate` để lại file trong temp | trái tuyên bố "mật/tự xoá" | xoá file output sau khi gửi |
| 19 | Extension trỏ `popup.html` không tồn tại | extension **không cài được** | dựng lại MV3 + offscreen document |
| 20 | `locustfile` mỗi user poll phòng của chính mình | load test **vô nghĩa** | đo đúng WS speaker + WS listener |
| 21 | `nginx` thiếu timeout WS, `Connection: upgrade` vô điều kiện | WS đứt sau 60s, upload >1MB lỗi | `map` + `proxy_read_timeout 3600s` + `client_max_body_size` |
| 22 | Không có git/test/README | lỗi tích luỹ không ai biết | `git init`, 77 test, tài liệu này |
| 23 | `load_audio_16k` gọi `librosa` trước | đọc MP3 có thể **treo >4 phút** (librosa → audioread → ffmpeg subprocess) | ưu tiên `soundfile` + `scipy.resample_poly`, fail-fast nếu file không tồn tại |
| 24 | Model nội bộ `models/` bị bỏ qua (load theo ID HuggingFace) | "offline 100%" vẫn phụ thuộc cache HF | `local_model_dir()` + `resolve_nmt_path()`, `download_offline_models.py` tải thẳng vào `models/` |
| 25 | `sentencepiece` không đọc được đường dẫn có dấu tiếng Việt | tokenizer báo `Unable to load vocabulary from file` khi repo nằm trong `F:\5 bài test\...` | trả về **đường dẫn tương đối ASCII**, fallback cache HF + cảnh báo |
| 26 | CPU final beam = 2 | đo thực tế VinAI fp32 tốn **~5–17s/câu** trên CPU | mặc định CPU beam = 1 |
| 27 | CT2 làm decoder **lặp vô nghĩa** — thử cả `int8_float32` và `float32` đều hỏng | nếu bật mặc định thì bản dịch thành rác mà không báo lỗi; lời hứa "nhanh 4-5x" trong code gốc là sai | CT2 **mặc định TẮT** + self-test khi khởi động + `looks_degenerate()` tự tắt sau 3 lần sinh rác |
| 28 | CLI `ct2-transformers-converter` lỗi `unexpected keyword argument 'dtype'` | không convert được CT2 trên cặp phiên bản transformers/ctranslate2 hiện tại | script tự vá (`dtype` ↔ `torch_dtype`) rồi gọi Python API, kèm bước verify |
| 29 | PWA đổ **cả EN + VI vào cả 2 màn hình** | trái yêu cầu "MH1 chỉ sub EN, MH2 chỉ bản dịch VI" | tách dòng theo từng màn hình + cập nhật VI tại chỗ khi bản dịch về sau |
| 30 | Đợi đủ ASR **và** NMT mới gửi câu | chữ EN hiện sau ~14.5s dù ASR chỉ mất 1.7s | gửi `final` (EN) ngay, gửi `{"kind":"vi"}` sau |
| 31 | Chạy ASR partial song song với lúc chốt câu | hai tác vụ tranh CPU → cả hai chậm | tạm dừng partial trong lúc chốt câu |

---

## 8. Hạn chế đã biết

- **CPU chưa đạt realtime với model gốc.** Đo thực tế trên máy này (CPU, fp32, beam=1):
  **~5–17s cho 1 câu** (VinAI 448M). Đường tăng tốc CT2 đã bị tắt vì **làm hỏng chất lượng**
  (thử cả int8_float32 và float32 — xem mục 1E). Muốn realtime cần: GPU, hoặc một model NMT
  nhỏ/đã tối ưu khác. Hệ thống **không che giấu** chuyện này: `/health`, `nmt.stats()` và
  thanh trạng thái desktop đều hiện engine đang dùng và lý do.
- **Đường dẫn repo không nên có dấu tiếng Việt.** `sentencepiece` (thư viện C++ của VinAI)
  trên Windows **không đọc được** đường dẫn chứa ký tự ngoài ASCII — tokenizer sẽ báo
  `Unable to load vocabulary from file`. `src/config.py:local_model_dir()` đã tự xử lý bằng
  cách trả về **đường dẫn tương đối ASCII** (hoặc fallback sang cache HuggingFace), nhưng
  cách chắc chắn nhất là chuyển repo sang thư mục không dấu, ví dụ
  `F:\projects\envi-stream-translator`. (Repo hiện tại nằm trong `F:\5 bài test\...`.)
- **Chỉ EN→VI** (đúng phạm vi). Không two-way, không đa ngôn ngữ.
- Độ trễ thực tế của cascade Whisper→NMT→TTS là **~1.5–3s** (khi NMT đã tối ưu), không phải
  "1s" như marketing. Số đo thật nằm ở `/metrics`.
- Diarization là heuristic MFCC + centroid: đủ để gán nhãn "ai nói câu nào", **không** thay
  thế pyannote cho hội nghị nhiều người nói chồng tiếng.
- `models/` không nằm trong git (1.7GB) — chạy `scripts/download_offline_models.py` sau khi
  clone; script này tải thẳng vào `models/` để chạy offline thật, không phụ thuộc cache HF.
- Cần `pip install qrcode[pil]` để có ảnh QR (không có thì trả về link, không vỡ).
- Extension Chrome chưa được test end-to-end trên Chrome thật (chỉ test tĩnh + VM giả lập).

---

## 9. Tối ưu tốc độ — số đo thực tế

Mọi con số dưới đây đo trên chính máy này (12 CPU logic, không GPU), audio tiếng Anh thật
qua `scripts/push_audio_ws.py`.

### Đã áp dụng (an toàn, không mất chất lượng)

| Tối ưu | Trước | Sau | Ghi chú |
|---|---|---|---|
| `torch.inference_mode()` thay `no_grad()` | 2706ms | **1125ms** | NMT nhanh 2.4x, miễn phí |
| Gửi **EN ngay**, VI gửi sau (`kind:"vi"`) | chờ đủ ASR+NMT ~14.5s | **EN sau 1.7–2.2s** | MH1 có chữ gần như tức thì |
| Tắt VAD nội bộ của Whisper | 1.29s | **1.09s** | kết quả nhận dạng giống hệt |
| Không chạy ASR partial trong lúc chốt câu | — | — | tránh 2 tác vụ tranh CPU |
| Không dịch partial (mặc định) | — | — | NMT rảnh cho câu final; bật `PARTIAL_VI=1` nếu muốn |
| Warm-up NMT lúc tải model | — | — | câu thật đầu tiên không chịu ~1–2s khởi tạo |

**Kết quả đo cuối** (1 câu ngắn 3s): EN sau **1.7s**, VI sau **+3.5s** (tổng 5.1s).
Trước khi tối ưu: EN+VI chỉ hiện sau **~14.5s**.

### Đã thử và **TỪ CHỐI** vì chất lượng/tốc độ (đo trên chính máy này)

| Phương án | Tốc độ đo được | Chất lượng | Vì sao từ chối |
|---|---|---|---|
| CTranslate2 int8 | nhanh ~4x | **rác** | sinh câu lặp vô nghĩa (`"Chúng Chúng Chúng chúng..."`); thử cả `int8_float32` và `float32` — cả hai đều hỏng |
| CTranslate2 float32 | 10.7s/câu | **rác** | vẫn lặp ⇒ lỗi ở bộ convert mBART, không phải ở lượng tử hoá |
| torch int8 dynamic | nhanh ~25–40% | **cụt đuôi** | chỉ trùng **72%** từ với fp32 (`"...triển khai sản xuất."` → `"...triển khai"`) |
| `Helsinki-NLP/opus-mt-en-vi` (77M) | 2206ms/câu | **sai nghĩa** | `"latency"` → `"khoan dung"` / `"khoan hồng"`; mất chữ "mobile" |
| `VietAI/envit5-translation` (T5-base ~220M) | **3163ms/câu (chậm hơn)** | BLEU **64.0** | chậm hơn VinAI mà tệ hơn; `"deployment plan"` → `"kế hoạch triển khai **quân**"` (ảo giác) |
| **ONNX Runtime fp32** (optimum export) | **7870ms/câu (chậm 2.2x)** | BLEU 74.0 (y hệt) | chất lượng không đổi nhưng **chậm hơn PyTorch** ⇒ không có lợi ích |

⇒ **Giữ VinAI en2vi-v2 fp32** (`BLEU 74.0 | chrF 81.5`). Muốn nhanh hơn nữa thì phải **GPU**.

### 5 nhóm cách tăng tốc — xếp theo hiệu quả thực tế

| # | Cách | Hiệu quả đo được | Mất chất lượng? |
|---|---|---|---|
| **1** | **Đóng ứng dụng khác + chỉ chạy 1 tiến trình** (server **hoặc** desktop) | **3x** (NMT 3.5s → 1.1s) | Không |
| **2** | `torch.inference_mode()` + tắt VAD + không dịch partial + gửi EN trước | NMT 2.4x, EN hiện sau 1.7s | Không |
| **3** | Giảm `FINAL_SILENCE=0.5`, `MAX_SEG=5`, `PARTIAL_EVERY=0.5` | bản dịch bắt đầu sớm hơn ~0.3–0.5s | Không |
| **4** | **GPU** (nếu có) | 10–30x cho NMT | Không |
| **5** | Lượng tử hoá / model nhỏ hơn | 1.2–4x | **CÓ** — cả 5 phương án đã thử đều hỏng (bảng trên) |

**Cách tự đo lại** (đừng tin lời, hãy đo):
```powershell
python scripts/bench_nmt_quality.py     # BLEU/chrF + ms/câu của từng model
python scripts/bench_optimize.py        # ASR: VAD on/off; NMT: fp32 vs int8
python scripts/bench_nmt_models.py      # so model nhỏ hơn
python scripts/bench_onnx.py            # ONNX Runtime (fp32 + int8)
python scripts/push_audio_ws.py --file out/short_en.mp3   # độ trễ thật end-to-end
```

### ⚠️ Cảnh báo quan trọng về máy

Đo được: cùng một câu, NMT mất **1.1s khi máy rảnh** nhưng **3.5s khi có tiến trình khác
cũng giữ model**. Nguyên nhân là áp lực RAM (mỗi tiến trình giữ ~1.8GB cho VinAI).
**Chỉ chạy MỘT trong hai**: server (`uvicorn`) **hoặc** app desktop — đừng chạy cả hai cùng lúc,
và nên đóng bớt trình duyệt/ứng dụng nặng khi dịch trực tiếp.

---

## 10. Giao diện 2 màn hình
| Màn hình | Nội dung | Nguồn dữ liệu |
|---|---|---|
| **MÀN HÌNH 1** | **Chỉ phụ đề tiếng Anh** (EN) | `partial` (chữ chạy) + `final` (câu chốt) |
| **MÀN HÌNH 2** | **Chỉ bản dịch tiếng Việt** (VI) | `{"kind":"vi", id, vi}` — đến sau `final` vài giây |

Cả trang người nghe (`static/room/index.html`) và PWA (`static/mobile/index.html`) đều theo
đúng quy tắc này; khi bản dịch chưa xong, MH2 hiện `dang dich...` rồi cập nhật **tại chỗ**
(không sinh dòng trùng, không nhảy vị trí).

---

## 11. Dùng GPU miễn phí mà **máy bạn vẫn trình diễn được**

Trả lời ngắn: **được, và máy bạn còn nhẹ hơn hiện tại.** Model nặng (NMT 1.8GB) chuyển lên
cloud; máy bạn chỉ còn trình duyệt (hoặc ASR nhẹ). Chi tiết thuê GPU ở `docs/GPU_RENTAL.md`.

### 3 kiến trúc — cái gì chạy ở đâu

| | Máy bạn chạy | Cloud GPU chạy | RAM máy bạn | Độ trễ/câu | Riêng tư |
|---|---|---|---|---|---|
| **1. Toàn bộ ở cloud** | chỉ trình duyệt | ASR + NMT + TTS | ~0 (chỉ Chrome) | ~0.5–0.8s | audio **rời máy** |
| **2. HYBRID (khuyến nghị)** | ASR + TTS + giao diện | **chỉ NMT** | **~300MB** (đo thật: 302MB vs 2202MB) | ~1.1s + 0.2s | **audio KHÔNG rời máy**, chỉ text |
| **3. Toàn bộ ở máy** (hiện tại) | tất cả | không | ~2.2GB | 5–9s | không rời máy |

### Cách bật kiến trúc 2 (đã code sẵn, chỉ 1 biến môi trường)

```powershell
# 1) Lấy URL GPU miễn phí: chạy scripts/colab_kaggle_server.py trong Colab/Kaggle
#    (hoặc `modal deploy modal_app.py`) -> được URL https://...
# 2) Trên máy bạn: chỉ gửi TEXT lên đó để dịch
set NMT_REMOTE_URL=https://<url-gpu>
python desktop_app_v2.py        # hoặc run_desktop_v2.bat
```
Khi đó máy bạn **không tải model NMT nữa** (nhẹ 1.9GB RAM, không tốn CPU để dịch), nhưng
vẫn giữ được: mic, phụ đề EN, giao diện 2 màn hình, xuất file, tóm tắt.

Kiểm chứng đã chạy thật trong repo:
- `tests/test_remote_nmt.py` — 7 test cho giao thức gọi GPU từ xa (kể cả khi máy GPU chết
  thì mic vẫn chạy, chỉ trả chuỗi rỗng chứ không vỡ luồng)
- Đo live 2 tiến trình: máy "yếu" **302MB** gọi máy "GPU" **2202MB** → trả về đúng
  `"Chúng ta cần kiểm tra ngân sách trước thứ Sáu."`
- `POST /translate` — endpoint để máy khác gọi vào (chỉ nhận text, không nhận audio)

### 2 file dùng GPU miễn phí (viết sẵn)

| File | Nền tảng | Miễn phí | Có URL public? |
|---|---|---|---|
| `scripts/colab_kaggle_server.py` | Colab / Kaggle | Kaggle 30h/tuần, Colab phiên ngắn | ✅ qua tunnel cloudflared (script tự mở và in URL) |
| `modal_app.py` | Modal | $30/tháng + grant sinh viên tới $10k | ✅ URL sẵn, ổn định hơn |

**Điểm hay:** URL cloud là `https://` nên **mic chạy được cả trên điện thoại** — điều mà
`http://<ip-LAN>` không làm được.

**Điểm cần biết:** phiên notebook có giới hạn thời gian (Kaggle ~9–12h, Colab ngắn hơn) →
phù hợp demo/bảo vệ, không phù hợp chạy 24/7. Và mọi phương án cloud đều làm **audio hoặc
text rời khỏi máy** → không dùng cho chế độ họp mật thật (xem `docs/GPU_RENTAL.md` mục 6).

### Kết quả đo thật trên Kaggle T4 (đã chạy qua tunnel công khai)

| | CPU (máy 12 nhân) | **Kaggle T4** |
|---|---|---|
| Engine NMT | `hf-cpu` | **`hf-cuda`** |
| ASR | `tiny.en` | **`large-v3-turbo`** (model xịn nhất) |
| NMT mỗi câu | 1125–2857 ms | **172 ms** (min 148, max 246) |
| Nhanh hơn | — | **6.5× – 16.6×** |
| Chất lượng | BLEU 74.0 | **BLEU 74.0** (không đổi) |

8/8 câu test dịch đúng, kể cả thuật ngữ khó (`latency` → `độ trễ`). Thời gian thực tế từ máy
người dùng (gồm cả vòng qua Cloudflare → Kaggle) là **~400–500 ms/câu**.

Tự đo lại bất cứ lúc nào:
```powershell
python scripts/bench_gpu_remote.py --url https://<ten>.trycloudflare.com
```
Script in ra: `server_ms` (GPU dịch thật), thời gian từ máy bạn (gồm mạng), BLEU/chrF, và bảng
so sánh CPU vs GPU — đủ số liệu để đưa vào chương đánh giá của khóa luận.

### Đã tích hợp vào hệ thống tới đâu

| Việc | Trạng thái |
|---|---|
| Chuyển NMT sang GPU từ xa | ✅ **tự động** — chỉ cần có URL |
| Server local (`app/server.py`) | ✅ đã nối qua `build_nmt()` |
| App desktop (`desktop_app_v2.py`) | ✅ có ô **GPU THUÊ** để dán URL + nút **KIỂM TRA + LƯU** + hiện `✔ GPU (hf-cuda)` |
| Demo Gradio / Saydi | ✅ đã nối |
| Lưu URL giữa các lần chạy | ✅ ghi vào `gpu_url.txt` — không phải gõ lại |
| Phát hiện URL chết | ✅ hiện `✘ GPU không kết nối được`; **mic + phụ đề EN vẫn chạy** |
| Bật phiên Kaggle | ❌ **thủ công** — Kaggle bắt buộc có người đăng nhập bấm Run |
| URL đổi mỗi phiên Kaggle | ❌ phải dán lại URL mới (Kaggle cấp URL khác mỗi phiên) |

**Cách dùng từ giờ (3 bước):**
1. Kaggle: chạy cell → **copy URL** in ra
2. Mở app desktop → dán URL vào ô **GPU THUÊ** → bấm **KIỂM TRA + LƯU**
   (thấy `✔ GPU (hf-cuda)` là đúng) → **khởi động lại app**
3. Các lần sau: **chỉ cần mở app** — URL đã lưu trong `gpu_url.txt`

Không thích dùng UI thì sửa trực tiếp file `gpu_url.txt` (1 dòng URL, để trống = dùng CPU máy).
Hoặc đặt biến môi trường `NMT_REMOTE_URL` (ưu tiên cao nhất, tiện cho 1 phiên tạm).

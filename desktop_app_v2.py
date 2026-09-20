"""Desktop ONLY - Nghe hoi thoai EN -> Sub EN (MH1) -> Sub VI (MH2) -> Xuat TXT/SRT/VTT.
Chay: python desktop_app_v2.py
Da gon theo huong desktop-realtime: khong server/docker/mobile/TTS/doc/summarize.

Nang cap theo loi (core src/ da duoc viet lai):
1. KHONG con tu ep model ASR nua: model lay tu `DEFAULT.resolve_asr_model(use_cuda)`
   -> may co GPU chay `large-v3-turbo`, may CPU chay `tiny.en` (hoac `ASR_MODEL` env).
2. MOI tham so (partial / chot im / ep chot / nguong noi / tran caption) lay tu
   `src.config.DEFAULT` - khong hardcode trong app.
3. Tuong quan caption bang ID ON DINH (`LiveSession` tra `id`), khong dung index
   -> cat bot cau cu (tran caption) khong con lam dich lech dong / lech nguoi noi.
4. Chon NGUON AM THANH: MIC that hoac AM THANH HE THONG (WASAPI loopback)
   -> dich duoc Zoom / Teams / Meet / YouTube vi loopback thu MOI am thanh ra loa.
5. AI Context Engine (kieu Saydi): kich ban + tu khoa / ten rieng + boi canh cuoc hop
   + tu dien EN=VI (toi da 50) -> nap vao ASR `initial_prompt` va glossary cua NMT.
6. Xuat TXT (EN/VI/ca hai), SRT va VTT voi timestamp THAT, don dieu, khong chong lan.
"""
import os

# Hop mat / offline: phai dat TRUOC khi import src.config (DEFAULT duoc tao luc import).
os.environ["OFFLINE"] = "1"
os.environ["CONFIDENTIAL"] = "1"

import time
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from src.config import DEFAULT, resolve_nmt_remote, save_nmt_remote, check_remote

# 16 kHz la chuan cua ASR; lay tu config, khong hardcode.
SR = DEFAULT.sample_rate

# Thoi luong toi thieu 1 cue phu de (SRT/VTT) - chi de file doc duoc, khong phai tham so ASR.
MIN_CUE_SEC = 1.2

# dark professional theme
BG = "#0b1020"
PANEL = "#151d33"
CARD = "#1e293b"
ACCENT = "#0b5cff"
EN_COLOR = "#7dd3fc"
VI_COLOR = "#86efac"
WARN = "#fcd34d"
TXT_FG = "#e5e7eb"

# AI Context Engine: 4 kich ban cua Saydi (event la mac dinh)
SCENARIOS_UI = [("Hội thảo / Sự kiện", "event"),
                ("Công nghệ / Kỹ thuật", "tech"),
                ("Kinh doanh / Đàm phán", "sales"),
                ("Bài giảng / Đào tạo", "education")]
SCEN_LABEL = {k: v for v, k in SCENARIOS_UI}
SCEN_KEY = {v: k for v, k in SCENARIOS_UI}

LOOPBACK_GROUP = "ÂM THANH HỆ THỐNG (Zoom/Teams/Meet/YouTube)"

captions = []  # [{id,en,vi,speaker,t,t_start,t_end,asr_ms,nmt_ms}]
live = None
pipe_ready = False
pipe_error = None
pending_context = {}   # ngu canh nguoi dung dat TRUOC khi model tai xong

q_mic = queue.Queue(maxsize=30)
q_ui = queue.Queue(maxsize=120)
q_nmt = queue.Queue(maxsize=50)


def log_mic_error(where, e):
    import traceback, datetime
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic_error.log")
        # xoay đơn giản: >200KB thì xóa
        try:
            if os.path.exists(p) and os.path.getsize(p) > 200 * 1024:
                os.remove(p)
        except Exception:
            pass
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] {where}: {e}\n")
            f.write(traceback.format_exc() + "\n")
    except Exception:
        pass


def com_init():
    """WASAPI (soundcard) can COM duoc khoi tao TREN TUNG THREAD."""
    try:
        import ctypes
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass


com_init()


def resample_to_16k(buf, from_sr, to_sr=None):
    to_sr = to_sr or SR
    try:
        from src.audio_utils import resample_to_16k as _rs
        return _rs(buf, from_sr, to_sr)
    except Exception:
        import numpy as np
        if from_sr == to_sr or len(buf) == 0:
            return buf.astype("float32")
        ratio = from_sr / to_sr
        n_new = int(len(buf) / ratio)
        if n_new <= 0:
            return np.zeros(0, dtype="float32")
        x_old = np.linspace(0, 1, len(buf))
        x_new = np.linspace(0, 1, n_new)
        return np.interp(x_new, x_old, buf).astype("float32")


def parse_glossary(raw):
    """Doc box tu dien: moi dong `english = tiếng việt`. Tra (terms_dict, dong_loi)."""
    terms, bad = {}, []
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" in s:
            en, vi = s.split("=", 1)
        elif ":" in s:
            en, vi = s.split(":", 1)
        else:
            bad.append(s)
            continue
        en, vi = en.strip(), vi.strip()
        if not en or not vi:
            bad.append(s)
            continue
        terms[en.lower()] = vi
    return terms, bad


def _ts(sec, comma=True):
    """Timestamp SRT (dau phay) / VTT (dau cham)."""
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms > 999:
        ms = 999
    return f"{h:02d}:{m:02d}:{s:02d}{',' if comma else '.'}{ms:03d}"


def build_cues(rows):
    """Cue (start, end, text, speaker) tu t_start/t_end THAT: don dieu, khong chong lan."""
    if not rows:
        return []
    t0 = rows[0].get("t_start") or time.time()
    out, prev_end = [], 0.0
    for c in rows:
        txt = (c.get("vi") or c.get("en") or "").strip()
        if not txt:
            continue
        s = max(0.0, float(c.get("t_start") or t0) - t0)
        te = c.get("t_end")
        e = (float(te) - t0) if te else (s + MIN_CUE_SEC)
        if s < prev_end:            # cue truoc ket thuc muon hon -> day cue nay ra sau
            s = prev_end
        if e < s + MIN_CUE_SEC:     # dam bao thoi luong toi thieu
            e = s + MIN_CUE_SEC
        prev_end = e
        out.append((s, e, txt, c.get("speaker", "Speaker 1")))
    return out


def nmt_worker():
    """Worker nền: chỉ dịch EN->VI, không bao giờ chặn mic.
    Final dùng accurate=True (beam cao, chuẩn nghĩa nhất), vẫn nhanh vì chạy nền.
    Tương quan bằng caption ID -> cắt bớt câu cũ không làm dịch lệch dòng."""
    while True:
        try:
            job = q_nmt.get()
        except Exception:
            continue
        try:
            if live is None or job[0] != "final":
                continue
            _, cid, en = job
            if not en or not en.strip():
                continue
            t0 = time.time()
            vi, ms, info = live.translate(en, accurate=True)
            total = (time.time() - t0) * 1000
            q_ui.put(("vi_final", {"cid": cid, "en": en, "vi": vi,
                                   "scenario": info.get("scenario", "event"),
                                   "nmt_ms": ms, "total_ms": total}))
        except Exception as e:
            log_mic_error("nmt-worker", e)
            continue


def load_models_bg(status_cb):
    global live, pipe_ready, pipe_error
    try:
        import torch
        from src.asr import FasterWhisperASR
        from src.nmt import NMTTranslator
        from src.live_session import LiveSession
        status_cb("Đang tải model offline (lần đầu 1-2 phút)...")
        use_cuda = torch.cuda.is_available()
        try:
            torch.set_num_threads(max(1, min(os.cpu_count() or 4, 8)))
            torch.set_num_interop_threads(1)
        except Exception:
            pass
        # --- ASR: model / compute / beam / language / gate deu tu config ---
        asr_model = DEFAULT.resolve_asr_model(use_cuda)
        compute = DEFAULT.resolve_compute(use_cuda)
        device = "cuda" if use_cuda else "cpu"
        final_beams = DEFAULT.resolve_final_beams(use_cuda)
        asr = FasterWhisperASR(asr_model, device=device, compute_type=compute,
                               beam_size=DEFAULT.asr_beam, language=DEFAULT.asr_language,
                               vad_filter=DEFAULT.asr_vad_filter,
                               gate_rms=DEFAULT.asr_gate_rms)
        # --- NMT: uu tien MAY GPU THUE neu co NMT_REMOTE_URL (chi gui TEXT),
        #     nguoc lai chay VinAI tai may. Xem src/nmt.py:build_nmt() ---
        from src.nmt import build_nmt
        nmt = build_nmt(DEFAULT.nmt_model, DEFAULT.nmt_src, DEFAULT.nmt_tgt,
                        num_beams=DEFAULT.nmt_live_beams,
                        max_len=DEFAULT.nmt_max_len,
                        accurate_beams=final_beams,
                        ct2_path=DEFAULT.ct2_dir)
        nst = nmt.stats()
        engine = nst.get("engine") or getattr(nmt, "engine", "?")
        live = LiveSession(asr, nmt, None, sr=SR, mode=DEFAULT.mode,
                           partial_every_sec=DEFAULT.partial_every_sec, cfg=DEFAULT)
        # warm-up: 1s im lặng để chunk đầu không chậm (best-practice whisper_streaming)
        try:
            import numpy as np
            asr.transcribe(np.zeros(SR, dtype=np.float32), SR)
        except Exception:
            pass
        # ngu canh nguoi dung da dat truoc khi model tai xong
        if pending_context:
            try:
                live.set_context(**pending_context)
            except Exception as e:
                log_mic_error("pending-context", e)
        pipe_ready = True
        threading.Thread(target=nmt_worker, daemon=True).start()
        try:
            st = live.stats()
            q_ui.put_nowait(("ctx_info", {"scenario": st.get("scenario", "event"),
                                          "terms": st.get("terms", 0),
                                          "mode": st.get("mode", DEFAULT.mode)}))
        except Exception:
            pass
        ct2_warn = f" | CT2 lỗi: {nst.get('ct2_error')}" if nst.get("ct2_error") else ""
        status_cb(f"Sẵn sàng (offline, ASR {asr_model} @ {device}/{compute}, "
                  f"NMT {engine} beam live={nst.get('live_beams')}/final={nst.get('final_beams')}, "
                  f"mode={DEFAULT.mode}){ct2_warn}. Bấm BẬT NGHE (F9).")
    except Exception as e:
        import traceback
        traceback.print_exc()
        pipe_error = str(e)
        status_cb(f"Lỗi tải model: {e}")


# ----------------------------------------------------------------- audio sources
def list_audio_sources():
    """Tra (mics, loops): mic that + thiet bi loopback WASAPI (ghi am thanh RA cua loa)."""
    com_init()
    import soundcard as sc
    mics = list(sc.all_microphones(include_loopback=False))
    allm = list(sc.all_microphones(include_loopback=True))
    loops = [m for m in allm if getattr(m, "isloopback", False)]
    if not loops:
        # ban soundcard cu khong dat co isloopback -> nhan dien bang id (loopback mang id cua LOA)
        mic_ids = {getattr(m, "id", None) for m in mics}
        loops = [m for m in allm if getattr(m, "id", None) not in mic_ids]
    return mics, loops


def default_loopback(loops):
    """Loopback cua LOA MAC DINH (khop id, roi khop ten), neu khong co thi lay cai dau."""
    if not loops:
        return None
    try:
        import soundcard as sc
        spk = sc.default_speaker()
        if spk is not None:
            for m in loops:
                if getattr(m, "id", None) and m.id == getattr(spk, "id", None):
                    return m
            for m in loops:
                if m.name == spk.name:
                    return m
    except Exception as e:
        log_mic_error("default-loopback", e)
    return loops[0]


def open_stream(dev):
    """Thu dung thiet bi da chon, thu samplerate [48000,44100,16000]. Tra (dev, sr)."""
    com_init()
    last_err = None
    for sr in (48000, 44100, 16000):
        try:
            # probe mở/đóng nhanh
            with dev.recorder(samplerate=sr, channels=1, blocksize=4096):
                pass
            return dev, sr
        except Exception as e:
            last_err = e
            continue
    kind = "Nguồn hệ thống" if getattr(dev, "isloopback", False) else "Mic"
    raise RuntimeError(
        f"{kind} '{dev.name}' không mở được (48000/44100/16000 đều lỗi: {str(last_err)[:150]}). "
        "Kiểm tra quyền Microphone Windows / loa đang bật, và đóng app đang giữ thiết bị.")


def _push_partial(chunk):
    """Partial nhanh: chi ASR (khong chan mic). Fallback sang API cong khai live.push()."""
    sim = getattr(live, "sim", None)
    fast = getattr(sim, "push_fast", None)
    if fast is not None:
        return fast(chunk)
    return live.push(chunk)


class App:
    def __init__(self, root):
        self.root = root
        root.title("Nghe EN → Sub EN + VI (Desktop Offline Realtime)")
        root.geometry("1120x860")
        root.configure(bg=BG)
        self.on = False
        self._gen = 0
        self._native_sr = 48000
        self._live_en = ""
        self.silence_start = None
        self._last_commit = time.time()
        self._last_voice = 0.0
        self._speaking = False
        self._last_rms = 0.0
        self._last_asr_txt = ""
        self._last_asr_time = 0.0
        self._asr_count = 0
        self._empty_count = 0
        self._local_id = 0                     # du phong khi final khong co id
        self._src_map = {}                     # nhan dropdown -> nguon
        self._src_kind = "mic"
        self._src_name = ""
        self._ctx_info = {"scenario": "event", "terms": 0, "mode": DEFAULT.mode}
        self._build_ui()
        # neu da luu URL may GPU -> kiem tra xem con song khong (hien thi len UI)
        self.root.after(800, self._probe_gpu_bg)
        threading.Thread(target=load_models_bg, args=(self.set_status,), daemon=True).start()
        self.root.after(200, self.poll_ui)
        self._bind_keys()

    # ---------- UI ----------
    def _build_ui(self):
        top = tk.Frame(self.root, bg=ACCENT)
        top.pack(fill="x")
        tk.Label(top, text="EN LIVE → VI", bg=ACCENT, fg="white",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=12, pady=8)
        self.btn_mic = tk.Button(top, text="●  BẬT NGHE  (F9)", font=("Segoe UI", 11, "bold"),
                                 bg="#22c55e", fg="#04120a", width=18, relief="flat",
                                 command=self.toggle_mic)
        self.btn_mic.pack(side="left", padx=6, pady=6)
        tk.Button(top, text="CHỐT CÂU (Space)", font=("Segoe UI", 10, "bold"),
                  bg=WARN, fg="#04120a", relief="flat",
                  command=self.force_finalize).pack(side="left", padx=4)
        tk.Button(top, text="THỬ FILE", font=("Segoe UI", 10, "bold"),
                  bg=EN_COLOR, fg="#04120a", relief="flat",
                  command=self.test_file).pack(side="left", padx=4)
        tk.Button(top, text="KT NGUỒN", font=("Segoe UI", 10, "bold"),
                  bg="#9fb3ff", fg="#04120a", relief="flat",
                  command=self.check_source).pack(side="left", padx=4)
        self.lbl_state = tk.Label(top, text="OFFLINE", bg="#04120a", fg=VI_COLOR,
                                  font=("Segoe UI", 9, "bold"), padx=8, pady=4)
        self.lbl_state.pack(side="right", padx=10)

        # --- chon nguon am thanh: MIC hoac AM THANH HE THONG (WASAPI loopback) ---
        srcbar = tk.Frame(self.root, bg=BG)
        srcbar.pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(srcbar, text="Nguồn nghe:", bg=BG, fg="#9fb3ff",
                 font=("Segoe UI", 10)).pack(side="left")
        self.src_var = tk.StringVar()
        self.src_box = tk.OptionMenu(srcbar, self.src_var, "")
        self.src_box.config(bg=CARD, fg="white", relief="flat", highlightthickness=0,
                            activebackground=ACCENT, activeforeground="white")
        self.src_box.pack(side="left", padx=6)
        tk.Button(srcbar, text="Quét lại", font=("Segoe UI", 9),
                  bg=CARD, fg="white", relief="flat",
                  command=self.refresh_sources).pack(side="left", padx=4)
        tk.Label(srcbar, text=(f"Ngưỡng nói {DEFAULT.speak_rms} • chốt im {DEFAULT.final_silence_sec}s "
                               f"• ép chốt {DEFAULT.max_seg_sec}s • partial {DEFAULT.partial_every_sec}s"),
                 bg=BG, fg="#64748b", font=("Segoe UI", 9)).pack(side="right")
        tk.Label(self.root, text=("Nguồn 'HỆ THỐNG' ghi âm thanh RA CỦA MÁY (WASAPI loopback): "
                                  "dịch được Zoom/Teams/Meet/YouTube vì nó thu MỌI âm thanh phát ra loa — "
                                  "chỉ cần loa đang phát."),
                 bg=BG, fg="#94a3b8", font=("Segoe UI", 9), anchor="w",
                 wraplength=1080, justify="left").pack(fill="x", padx=10)

        # --- AI Context Engine (Saydi) ---
        ctx = tk.Frame(self.root, bg=CARD)
        ctx.pack(fill="x", padx=10, pady=(6, 0))
        row1 = tk.Frame(ctx, bg=CARD)
        row1.pack(fill="x", padx=8, pady=(6, 2))
        tk.Label(row1, text="NGỮ CẢNH AI", bg=CARD, fg=WARN,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(row1, text="Kịch bản:", bg=CARD, fg="#9fb3ff",
                 font=("Segoe UI", 9)).pack(side="left", padx=(10, 2))
        self.sc_var = tk.StringVar(value=SCEN_LABEL["event"])
        sc_box = tk.OptionMenu(row1, self.sc_var, *[lbl for lbl, _ in SCENARIOS_UI])
        sc_box.config(bg=PANEL, fg="white", relief="flat", highlightthickness=0,
                      activebackground=ACCENT, activeforeground="white")
        sc_box.pack(side="left")
        tk.Label(row1, text="Từ khóa / Tên riêng:", bg=CARD, fg="#9fb3ff",
                 font=("Segoe UI", 9)).pack(side="left", padx=(10, 2))
        self.kw_var = tk.StringVar()
        tk.Entry(row1, textvariable=self.kw_var, width=24, bg="#020617", fg="white",
                 insertbackground="white", relief="flat").pack(side="left", ipady=3)
        tk.Label(row1, text="Bối cảnh cuộc họp:", bg=CARD, fg="#9fb3ff",
                 font=("Segoe UI", 9)).pack(side="left", padx=(10, 2))
        self.det_var = tk.StringVar()
        tk.Entry(row1, textvariable=self.det_var, width=30, bg="#020617", fg="white",
                 insertbackground="white", relief="flat").pack(side="left", ipady=3)
        tk.Button(row1, text="ÁP DỤNG NGỮ CẢNH", bg=ACCENT, fg="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=8, pady=4,
                  command=self.apply_context).pack(side="right")
        row2 = tk.Frame(ctx, bg=CARD)
        row2.pack(fill="x", padx=8, pady=(2, 6))
        tk.Label(row2, text="Từ điển EN = VI\n(mỗi dòng 1 thuật ngữ):", bg=CARD, fg="#9fb3ff",
                 font=("Segoe UI", 9), justify="left").pack(side="left", anchor="n")
        self.gloss_txt = tk.Text(row2, height=3, bg="#020617", fg=TXT_FG,
                                 font=("Consolas", 9), wrap="none", relief="flat",
                                 padx=6, pady=4, insertbackground="white")
        self.gloss_txt.pack(side="left", fill="x", expand=True, padx=6)
        self.gloss_txt.insert("1.0", "# ví dụ: latency = độ trễ\n")
        tk.Label(row2, text=(f"Tối đa {DEFAULT.glossary_max_terms} thuật ngữ.\n"
                             "Áp dụng được GIỮA PHIÊN,\nkhông cần khởi động lại."),
                 bg=CARD, fg="#64748b", font=("Segoe UI", 8),
                 justify="left").pack(side="left", anchor="n")

        # --- MAY GPU THUE (Kaggle/Colab/Modal): dan URL de dich tren GPU ---
        row3 = tk.Frame(ctx, bg=CARD)
        row3.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(row3, text="GPU THUÊ", bg=CARD, fg=WARN,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(row3, text="URL máy GPU:", bg=CARD, fg="#9fb3ff",
                 font=("Segoe UI", 9)).pack(side="left", padx=(10, 2))
        self.gpu_var = tk.StringVar(value=resolve_nmt_remote())
        tk.Entry(row3, textvariable=self.gpu_var, width=44, bg="#020617", fg="white",
                 insertbackground="white", relief="flat").pack(side="left", ipady=3)
        tk.Button(row3, text="KIỂM TRA + LƯU", bg="#22c55e", fg="#04120a",
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=8, pady=4,
                  command=self.check_gpu).pack(side="left", padx=6)
        tk.Button(row3, text="DÙNG MÁY NÀY (CPU)", bg=CARD, fg="#e5e7eb",
                  font=("Segoe UI", 9), relief="flat", padx=8, pady=4,
                  command=self.use_local_cpu).pack(side="left")
        self.gpu_lbl = tk.Label(row3, text="", bg=CARD, fg="#9fb3ff",
                                font=("Segoe UI", 9))
        self.gpu_lbl.pack(side="left", padx=6)
        tk.Label(ctx, text=("Dán URL https://...trycloudflare.com từ Kaggle/Colab rồi bấm "
                            "KIỂM TRA + LƯU.\nĐể trống = dịch ngay tại máy (CPU). "
                            "Đổi phiên Kaggle thì dán URL mới."),
                 bg=CARD, fg="#64748b", font=("Segoe UI", 8), justify="left").pack(
                     anchor="w", padx=10, pady=(0, 6))

        self.status = tk.Label(self.root, text="Đang khởi động...", bg=CARD,
                               fg=WARN, anchor="w", font=("Segoe UI", 10), padx=10, pady=6)
        self.status.pack(fill="x", padx=10, pady=6)

        meterbar = tk.Frame(self.root, bg=BG)
        meterbar.pack(fill="x", padx=10)
        self.meter_canvas = tk.Canvas(meterbar, height=10, bg="#020617", highlightthickness=0)
        self.meter_canvas.pack(fill="x", side="top")
        self.meter = tk.Label(meterbar, text="Nguồn: ... | ASR: ...", bg=BG,
                              fg="#9fb3ff", anchor="w", font=("Segoe UI", 9))
        self.meter.pack(fill="x")

        mid = tk.Frame(self.root, bg=BG)
        mid.pack(fill="both", expand=True, padx=10, pady=6)

        left = tk.Frame(mid, bg=PANEL, highlightthickness=0)
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        tk.Label(left, text="MÀN HÌNH 1 — NGHE TRỰC TIẾP (EN)", bg=PANEL,
                 fg=EN_COLOR, font=("Segoe UI", 11, "bold"), pady=6).pack()
        self.txt_en = tk.Text(left, bg="#020617", fg=TXT_FG, font=("Segoe UI", 11),
                              wrap="word", state="disabled", relief="flat",
                              padx=10, pady=8)
        self.txt_en.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        right = tk.Frame(mid, bg=PANEL, highlightthickness=0)
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))
        tk.Label(right, text="MÀN HÌNH 2 — DỊCH TRỰC TIẾP (VI)", bg=PANEL,
                 fg=VI_COLOR, font=("Segoe UI", 11, "bold"), pady=6).pack()
        self.txt_vi = tk.Text(right, bg="#020617", fg=TXT_FG, font=("Segoe UI", 11),
                              wrap="word", state="disabled", relief="flat",
                              padx=10, pady=8)
        self.txt_vi.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        bot = tk.Frame(self.root, bg=BG)
        bot.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(bot, text="Xong hội thoại →", bg=BG, fg="#9fb3ff",
                 font=("Segoe UI", 10)).pack(side="left")
        for label, mode, fmt in [("XUẤT TXT EN-VI (F5)", "both", "txt"),
                                 ("XUẤT EN", "en", "txt"),
                                 ("XUẤT VI", "vi", "txt"),
                                 ("XUẤT SRT", "vi", "srt"),
                                 ("XUẤT VTT (F6)", "vi", "vtt")]:
            tk.Button(bot, text=label, bg="#22c55e", fg="#04120a",
                      font=("Segoe UI", 9, "bold"), relief="flat", padx=8, pady=6,
                      command=lambda m=mode, f=fmt: self.export(m, f)).pack(side="left", padx=4)
        tk.Button(bot, text="XÓA NGAY (Ctrl+L)", bg="#ef4444", fg="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=8, pady=6,
                  command=self.clear_all).pack(side="left", padx=8)
        self.lat = tk.Label(bot, text="", bg=BG, fg="#9fb3ff", font=("Segoe UI", 9))
        self.lat.pack(side="right")
        self.refresh_sources()

    def _bind_keys(self):
        self.root.bind("<F9>", lambda e: self.toggle_mic())
        self.root.bind("<space>", lambda e: self.force_finalize() if not self._typing() else None)
        self.root.bind("<F5>", lambda e: self.export("both", "txt"))
        self.root.bind("<F6>", lambda e: self.export("vi", "vtt"))
        self.root.bind("<Control-l>", lambda e: self.clear_all())
        self.root.bind("<Control-L>", lambda e: self.clear_all())

    def _typing(self):
        w = self.root.focus_get()
        return isinstance(w, (tk.Text, tk.Entry))

    # ---------- status / queue ----------
    def set_status(self, t):
        try:
            q_ui.put_nowait(("status", t))
        except queue.Full:
            pass

    # ---------- nguon am thanh ----------
    def refresh_sources(self):
        """Quet lai: nhom MIC (that) + nhom AM THANH HE THONG (loopback WASAPI)."""
        com_init()
        self._src_map = {}
        mics, loops = [], []
        try:
            mics, loops = list_audio_sources()
        except Exception as e:
            log_mic_error("refresh-sources", e)
        menu = self.src_box["menu"]
        menu.delete(0, "end")
        first = None
        menu.add_command(label="── MICRO (mic thật) ──", state="disabled")
        for m in mics:
            lbl = f"MIC — {m.name}"
            self._src_map[lbl] = {"kind": "mic", "dev": m, "name": m.name}
            menu.add_command(label=lbl, command=lambda v=lbl: self.src_var.set(v))
            first = first or lbl
        menu.add_separator()
        menu.add_command(label=f"── {LOOPBACK_GROUP} ──", state="disabled")
        if loops:
            auto = f"HỆ THỐNG — loa mặc định ({default_loopback(loops).name})"
            self._src_map[auto] = {"kind": "loop_auto", "dev": None, "name": "loa mặc định"}
            menu.add_command(label=auto, command=lambda v=auto: self.src_var.set(v))
            first = first or auto
        for m in loops:
            lbl = f"HỆ THỐNG — {m.name} [Loopback]"
            self._src_map[lbl] = {"kind": "loop", "dev": m, "name": m.name}
            menu.add_command(label=lbl, command=lambda v=lbl: self.src_var.set(v))
            first = first or lbl
        if not self._src_map:
            lbl = "(không thấy nguồn âm thanh nào — bấm Quét lại)"
            self._src_map[lbl] = None
            menu.add_command(label=lbl, command=lambda: None)
            self.src_var.set(lbl)
            return
        # mac dinh: mic dau tien (uu tien khong phai "Array"), nhu ban cu
        pick = None
        for m in mics:
            if "Array" not in m.name:
                pick = f"MIC — {m.name}"
                break
        if pick is None:
            pick = first
        self.src_var.set(pick)

    def resolve_source(self):
        """Tra (dev, kind, nhan) cho lua chon hien tai; (None, kind, nhan) neu khong co."""
        ent = self._src_map.get(self.src_var.get())
        if ent is None:
            self.refresh_sources()
            ent = self._src_map.get(self.src_var.get())
        if not ent:
            return None, "mic", ""
        if ent["kind"] == "loop_auto":
            try:
                _, loops = list_audio_sources()
            except Exception as e:
                log_mic_error("resolve-loopback", e)
                loops = []
            d = default_loopback(loops)
            return d, "loop", (f"âm thanh hệ thống ({d.name})" if d else "")
        if ent["kind"] == "loop":
            return ent.get("dev"), "loop", f"âm thanh hệ thống ({ent['name']})"
        return ent.get("dev"), "mic", f"mic ({ent['name']})"

    def toggle_mic(self):
        if self.on:
            self.stop_mic()
        else:
            if getattr(self, "_starting", False):
                return
            self._starting = True
            try:
                self.start_mic()
            finally:
                self._starting = False

    def start_mic(self):
        if not pipe_ready:
            messagebox.showinfo("Chờ chút", "Model offline chưa tải xong, đợi 1-2 phút.")
            return
        dev, kind, name = self.resolve_source()
        if dev is None:
            messagebox.showerror("Lỗi nguồn", "Không thấy nguồn âm thanh nào. Bấm Quét lại.")
            return
        try:
            dev, sr = open_stream(dev)
        except Exception as e:
            messagebox.showerror("Lỗi nguồn", str(e))
            self.set_status(f"Lỗi nguồn: {str(e)[:150]}")
            return
        self._native_sr = sr
        self._src_kind = kind
        self._src_name = name
        self.on = True
        self._gen += 1
        gen = self._gen
        try:
            while True:
                q_mic.get_nowait()
        except Exception:
            pass
        try:
            while True:
                q_nmt.get_nowait()
        except Exception:
            pass
        self._last_commit = time.time()
        self._last_voice = time.time()
        self._speaking = False
        self.silence_start = None
        self.btn_mic.config(text="■  ĐANG NGHE - BẤM ĐỂ DỪNG", bg="#ef4444", fg="white")
        self.lbl_state.config(text="● LIVE", fg="#ef4444")
        hint = ("nói tiếng Anh đi." if kind == "mic"
                else "mở Zoom/Teams/Meet/YouTube cho âm thanh phát ra loa.")
        self.set_status(f"Đang nghe {name} ({sr}Hz → 16k)... {hint}")
        threading.Thread(target=self._sc_loop, args=(dev, sr, gen), daemon=True).start()
        threading.Thread(target=self.audio_loop, args=(gen,), daemon=True).start()

    def _sc_loop(self, dev, sr, gen):
        com_init()
        import numpy as np
        fails = 0
        try:
            with dev.recorder(samplerate=sr, channels=1, blocksize=4096) as rec:
                while self.on and gen == self._gen:
                    try:
                        data = rec.record(numframes=4096)
                        fails = 0
                    except Exception as e:
                        fails += 1
                        if fails == 1:
                            log_mic_error("wasapi-record", e)
                        if fails > 20:
                            q_ui.put(("status", f"Lỗi thu WASAPI liên tục ({fails}). Xem mic_error.log"))
                            self.on = False
                            q_ui.put(("mic_dead", ""))
                            break
                        continue
                    if not self.on or gen != self._gen:
                        break
                    mono = data[:, 0] if data.ndim > 1 else data.flatten()
                    chunk16 = resample_to_16k(mono.astype("float32"), sr, SR)
                    if len(chunk16):
                        try:
                            q_mic.put_nowait((chunk16 * 32768.0).astype("int16"))
                        except queue.Full:
                            try:
                                q_mic.get_nowait()
                            except Exception:
                                pass
                            try:
                                q_mic.put_nowait((chunk16 * 32768.0).astype("int16"))
                            except Exception:
                                pass
        except Exception as e:
            log_mic_error("wasapi-open", e)
            q_ui.put(("status", f"Lỗi thu WASAPI: {str(e)[:150]}."))
            q_ui.put(("mic_dead", ""))

    def _emit_final(self):
        """Chot cau (ASR nhanh) roi day sang UI; NMT chay o worker nen."""
        try:
            fin = live.finalize_fast() if live else None
        except Exception as e:
            log_mic_error("finalize", e)
            return
        if fin and fin.get("en"):
            q_ui.put(("final_en", fin))

    def stop_mic(self):
        self._gen += 1
        self.on = False
        self._emit_final()
        self.btn_mic.config(text="●  BẬT NGHE  (F9)", bg="#22c55e", fg="#04120a")
        self.lbl_state.config(text="OFFLINE", fg=VI_COLOR)
        self.set_status("Đã dừng. Bấm XUẤT TXT/SRT/VTT để lưu, XÓA NGAY để hủy dữ liệu.")

    def audio_loop(self, gen):
        import numpy as np
        while self.on and gen == self._gen and live:
            try:
                raw = q_mic.get(timeout=0.5)
            except Exception:
                continue
            if gen != self._gen:
                break
            chunk = raw.flatten().astype("float32") / 32768.0
            try:
                prev_emit = live.sim.last_emit
                ev = _push_partial(chunk)
                if live.sim.last_emit != prev_emit:
                    self._asr_count += 1
                    self._last_asr_time = time.time()
                    if ev:
                        self._last_asr_txt = ev.get("en", "")
                    else:
                        self._empty_count += 1
                if ev:
                    try:
                        q_ui.put_nowait(("partial_en", {"en": ev.get("en", "")}))
                    except queue.Full:
                        pass
                rms = float((chunk ** 2).mean() ** 0.5) if len(chunk) else 0.0
                self._last_rms = rms
                now = time.time()
                # endpointing theo THỜI GIAN (không đếm chunk), ngưỡng lấy từ config
                if rms >= DEFAULT.speak_rms:
                    self._speaking = True
                    self._last_voice = now
                    self.silence_start = None
                else:
                    if self._speaking and self.silence_start is None:
                        self.silence_start = now
                    if (self._speaking and self.silence_start
                            and now - self.silence_start >= DEFAULT.final_silence_sec):
                        self.silence_start = None
                        self._speaking = False
                        self._emit_final()
                        self._last_commit = now
                    elif self._speaking and now - self._last_commit > DEFAULT.max_seg_sec:
                        self._emit_final()
                        self._last_commit = now
            except Exception as e:
                log_mic_error("audio-loop", e)

    # ---------- UI update ----------
    def poll_ui(self):
        try:
            for _ in range(20):
                kind, data = q_ui.get_nowait()
                if kind == "status":
                    self.status.config(text=data)
                elif kind == "ctx_info":
                    self._ctx_info = {"scenario": data.get("scenario", "event"),
                                      "terms": data.get("terms", 0),
                                      "mode": data.get("mode", DEFAULT.mode)}
                elif kind == "mic_dead":
                    self.on = False
                    self.btn_mic.config(text="●  BẬT NGHE  (F9)", bg="#22c55e", fg="#04120a")
                    self.lbl_state.config(text="OFFLINE", fg=VI_COLOR)
                elif kind == "partial_en":
                    self.show_en_live(data.get("en", ""))
                elif kind == "final_en":
                    self.commit_final_en(data)
                elif kind == "vi_final":
                    self.patch_vi_final(data)
                elif kind == "gpu_check":
                    try:
                        data()          # data la ham callback (chay tren UI thread)
                    except Exception as e:
                        log_mic_error("gpu-check-ui", e)
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            rms = getattr(self, "_last_rms", 0.0)
            bars = int(min(1.0, rms * 60) * 100)
            self.meter_canvas.delete("all")
            w = self.meter_canvas.winfo_width() or 400
            self.meter_canvas.create_rectangle(0, 0, w * bars / 100, 10, fill="#22c55e", outline="")
            ago = time.time() - (self._last_asr_time or 0)
            src = "Mic" if self._src_kind == "mic" else "Hệ thống"
            if not self.on:
                m = f"{src}: tắt | ASR chạy {self._asr_count} lần, rỗng {self._empty_count} lần"
            elif rms < 0.002:
                m = (f"{src}: IM LẶNG (rms={rms:.4f}) — "
                     f"{'nói to lên!' if self._src_kind == 'mic' else 'cho âm thanh phát ra loa!'} | "
                     f"ASR cuối: {self._last_asr_txt[:50]} ({ago:.0f}s trước)")
            else:
                m = (f"{src}: ĐANG NGHE (rms={rms:.4f}) | "
                     f"ASR cuối: {self._last_asr_txt[:50]} ({ago:.0f}s trước)")
            self.meter.config(text=m)
        except Exception:
            pass
        self.root.after(200, self.poll_ui)

    def _append(self, widget, text):
        widget.config(state="normal")
        widget.insert("end", text + "\n")
        widget.see("end")
        widget.config(state="disabled")

    def _set_live_line(self, widget, txt):
        widget.config(state="normal")
        content = widget.get("1.0", "end").splitlines()
        if content and content[-1].startswith("... "):
            widget.delete("end-2l", "end-1l")
        if txt:
            widget.insert("end", f"... {txt}\n")
            widget.see("end")
        widget.config(state="disabled")

    def show_en_live(self, en):
        if not en:
            return
        self._live_en = en
        self._set_live_line(self.txt_en, en)
        self.status.config(text=f"TRỰC TIẾP: {en[:90]} ...")

    def _vi_text(self, cap):
        vi = (cap.get("vi") or "").strip()
        if vi:
            return vi
        if self._ctx_info.get("mode") == "transcribe":
            return "(chế độ transcribe — chỉ có EN)"
        return "(đang dịch...)"

    def _trim_captions(self):
        """Cat bot cau cu theo DEFAULT.max_captions. True neu co cat (phai ve lai)."""
        cut = False
        while len(captions) > DEFAULT.max_captions:
            captions.pop(0)
            cut = True
        return cut

    def commit_final_en(self, fin):
        en = (fin.get("en") or "").strip()
        if not en:
            return
        cid = fin.get("id")
        if cid is None:
            # du phong: van phai co ID ON DINH, khong bao gio dung index lam khoa
            self._local_id += 1
            cid = f"local-{self._local_id}"
        spk = fin.get("speaker", "Speaker 1")
        t = time.strftime("%H:%M:%S")
        now = time.time()
        cap = {"id": cid, "en": en, "vi": "", "speaker": spk, "t": t,
               "t_start": fin.get("t_start") or self._last_voice or now,
               "t_end": None, "asr_ms": fin.get("asr_ms", 0), "nmt_ms": 0}
        captions.append(cap)
        if self._trim_captions():
            self._redraw_en()
            self._redraw_vi()
        else:
            for widget in (self.txt_en, self.txt_vi):
                widget.config(state="normal")
                content = widget.get("1.0", "end").splitlines()
                if content and content[-1].startswith("... "):
                    widget.delete("end-2l", "end-1l")
                widget.config(state="disabled")
            self._append(self.txt_en, f"[{t}] {en}")
            self._append(self.txt_vi, "(đang dịch...)")
        try:
            q_nmt.put_nowait(("final", cid, en))
        except queue.Full:
            pass

    def patch_vi_final(self, d):
        """Gan ban dich vao DUNG caption theo id (khong dung index)."""
        cid = d.get("cid")
        vi = (d.get("vi") or "").strip()
        cap = None
        if cid is not None:
            for c in captions:
                if c.get("id") == cid:
                    cap = c
                    break
        if cap is None:
            # cau da bi cat do vuot tran caption -> ghi dong MOI, khong de len dong khac
            en = (d.get("en") or "").strip()
            if not en:
                return
            t = time.strftime("%H:%M:%S")
            now = time.time()
            cap = {"id": cid, "en": en, "vi": vi, "speaker": d.get("speaker", "Speaker 1"),
                   "t": t, "t_start": d.get("t_start") or now, "t_end": now,
                   "asr_ms": d.get("asr_ms", 0), "nmt_ms": d.get("nmt_ms", 0)}
            captions.append(cap)
            if self._trim_captions():
                self._redraw_en()
                self._redraw_vi()
            else:
                self._append(self.txt_en, f"[{t}] {en}")
                self._append(self.txt_vi, f"[{t}] {self._vi_text(cap)}")
            self._update_lat(cap, d)
            return
        cap["vi"] = vi
        cap["nmt_ms"] = d.get("nmt_ms", 0)
        cap["t_end"] = time.time()
        pos = captions.index(cap)
        # cập nhật đúng dòng (không vẽ lại toàn bộ -> không lag)
        try:
            w = self.txt_vi
            w.config(state="normal")
            lines = w.get("1.0", "end").splitlines()
            target = pos + 1  # 1-indexed; dong live "..." chi co o khung EN
            if 1 <= target <= len(lines):
                w.delete(f"{target}.0", f"{target}.end")
                w.insert(f"{target}.0", f"[{cap['t']}] {self._vi_text(cap)}")
            else:
                w.insert("end", f"[{cap['t']}] {self._vi_text(cap)}\n")
            w.see("end")
            w.config(state="disabled")
        except Exception:
            self._redraw_vi()
        self._update_lat(cap, d)

    def _update_lat(self, cap, d=None):
        d = d or {}
        nmt_ms = d.get("nmt_ms", cap.get("nmt_ms", 0)) or 0
        ci = self._ctx_info
        self.lat.config(text=(f"ASR {round(cap.get('asr_ms', 0) or 0)}ms + NMT {round(nmt_ms)}ms | "
                              f"{ci.get('scenario', 'event')} | {ci.get('terms', 0)} thuật ngữ | "
                              f"{len(captions)} câu"))

    def _redraw_en(self):
        w = self.txt_en
        w.config(state="normal")
        w.delete("1.0", "end")
        for c in captions:
            w.insert("end", f"[{c['t']}] {c['en']}\n")
        w.see("end")
        w.config(state="disabled")

    def _redraw_vi(self):
        w = self.txt_vi
        w.config(state="normal")
        w.delete("1.0", "end")
        for c in captions:
            w.insert("end", f"[{c['t']}] {self._vi_text(c)}\n")
        w.see("end")
        w.config(state="disabled")

    # ---------- AI Context Engine ----------
    def _probe_gpu_bg(self):
        """Khi mo app: kiem tra may GPU da luu trong gpu_url.txt con song khong."""
        url = resolve_nmt_remote()
        if not url:
            return

        def _work():
            info = check_remote(url, timeout=10)

            def _done():
                if not info.get("ok"):
                    self.gpu_lbl.config(text="✘ GPU không kết nối được", fg="#fca5a5")
                    return
                dev = info.get("device")
                if dev == "cuda":
                    self.gpu_lbl.config(text=f"✔ GPU ({info.get('engine')})", fg="#86efac")
                else:
                    self.gpu_lbl.config(text=f"⚠ không có GPU ({dev})", fg=WARN)
            q_ui.put(("gpu_check", _done))

        threading.Thread(target=_work, daemon=True).start()

    def check_gpu(self):
        """Kiem tra may GPU thue roi luu vao gpu_url.txt.

        Chi gui TEXT len GPU -> audio khong roi khoi may. May nay nhe RAM hon
        (khong giu model NMT 1.8GB).
        """
        url = (self.gpu_var.get() or "").strip().rstrip("/")
        if not url:
            self.use_local_cpu()
            return
        self.gpu_lbl.config(text="đang kiểm tra...", fg=WARN)
        self.root.update_idletasks()

        def _work():
            info = check_remote(url, timeout=12)
            def _done():
                if not info.get("ok"):
                    self.gpu_lbl.config(text="✘ không kết nối được", fg="#fca5a5")
                    messagebox.showerror(
                        "Không kết nối được máy GPU",
                        f"{url}\n\n{info.get('error')}\n\n"
                        "Kiểm tra:\n"
                        "• Cell Kaggle/Colab còn đang chạy không?\n"
                        "• URL có đúng không (đổi mỗi phiên)?\n"
                        "• Đã bật Internet cho notebook chưa?")
                    return
                dev = info.get("device") or "?"
                eng = info.get("engine") or "?"
                if dev == "cuda":
                    self.gpu_lbl.config(text=f"✔ GPU ({eng})", fg="#86efac")
                else:
                    self.gpu_lbl.config(
                        text=f"⚠ máy đó KHÔNG có GPU ({eng}/{dev})", fg=WARN)
                try:
                    save_nmt_remote(url)
                except Exception as e:
                    log_mic_error("save-gpu-url", e)
                messagebox.showinfo(
                    "Đã lưu",
                    f"Đã lưu URL vào gpu_url.txt\n\n"
                    f"engine : {eng}\ndevice : {dev}\nasr    : {info.get('asr')}\n\n"
                    "KHỞI ĐỘNG LẠI app để dùng GPU từ xa.\n"
                    "(Lúc đó chỉ TEXT được gửi lên GPU — audio không rời máy.)")
            q_ui.put(("gpu_check", _done))

        threading.Thread(target=_work, daemon=True).start()

    def use_local_cpu(self):
        """Tat che do GPU tu xa: dich ngay tai may (khong can Internet)."""
        self.gpu_var.set("")
        try:
            save_nmt_remote("")
        except Exception:
            pass
        self.gpu_lbl.config(text="đang dùng CPU của máy này", fg="#9fb3ff")
        messagebox.showinfo("Đã tắt GPU từ xa",
                            "Đã xoá URL trong gpu_url.txt.\n"
                            "Khởi động lại app để dịch ngay tại máy (CPU).")

    def apply_context(self):
        """Ap dung ngay giua phien: ASR initial_prompt + NMT glossary. Khong can restart."""
        scen = SCEN_KEY.get(self.sc_var.get(), "event")
        kw = self.kw_var.get().strip()
        det = self.det_var.get().strip()
        terms, bad = parse_glossary(self.gloss_txt.get("1.0", "end"))
        if bad:
            messagebox.showerror("Từ điển",
                                 "Dòng không hợp lệ (cần dạng 'english = tiếng việt'):\n"
                                 + "\n".join(bad[:8]))
            return
        if len(terms) > DEFAULT.glossary_max_terms:
            messagebox.showerror("Từ điển",
                                 f"Từ điển tối đa {DEFAULT.glossary_max_terms} thuật ngữ, "
                                 f"bạn nhập {len(terms)}. Bớt lại rồi áp dụng.")
            return
        payload = {"scenario": scen, "details": det, "keywords": kw,
                   "terms": terms or None}
        if live is None:
            pending_context.clear()
            pending_context.update(payload)
            self.set_status(f"Đã ghi nhớ ngữ cảnh ({scen}, {len(terms)} thuật ngữ) — "
                            "sẽ áp dụng ngay khi model tải xong.")
            return
        try:
            if not terms:
                live.ctx.clear_custom()      # box trống = xóa từ điển custom
            info = live.set_context(scenario=scen, details=det, keywords=kw,
                                    terms=terms or None, replace_terms=True)
        except ValueError as e:
            messagebox.showerror("Từ điển",
                                 f"Không áp dụng được: {e}. "
                                 f"Tối đa {DEFAULT.glossary_max_terms} thuật ngữ.")
            return
        except Exception as e:
            log_mic_error("apply-context", e)
            messagebox.showerror("Ngữ cảnh", f"Lỗi áp dụng ngữ cảnh: {e}")
            return
        self._ctx_info = {"scenario": info.get("scenario", scen),
                          "terms": info.get("terms", 0),
                          "mode": getattr(live, "mode", DEFAULT.mode)}
        prompt = "BẬT" if info.get("asr_prompt") else "TẮT"
        self.set_status(f"Đã áp dụng ngữ cảnh: kịch bản {info.get('scenario')} • "
                        f"{info.get('terms')} thuật ngữ • ASR prompt {prompt} "
                        "(tên riêng/jargon được ưu tiên). Không cần khởi động lại.")
        self.lat.config(text=(f"{self._ctx_info['scenario']} | "
                              f"{self._ctx_info['terms']} thuật ngữ | {len(captions)} câu"))

    # ---------- export / clear ----------
    def export(self, mode="both", fmt="txt"):
        rows = [c for c in captions if c.get("en") or c.get("vi")]
        if not rows:
            messagebox.showinfo("Trống", "Chưa có câu hội thoại nào.")
            return
        ext = {"srt": ".srt", "vtt": ".vtt"}.get(fmt, ".txt")
        p = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[("Text", "*.txt"), ("SRT", "*.srt"), ("VTT", "*.vtt"), ("All", "*.*")])
        if not p:
            return

        lines = []
        if fmt in ("srt", "vtt"):
            comma = (fmt == "srt")
            if not comma:
                lines += ["WEBVTT", ""]
            for i, (s, e, txt, spk) in enumerate(build_cues(rows), 1):
                lines += [str(i), f"{_ts(s, comma)} --> {_ts(e, comma)}",
                          f"[{spk}] {txt}", ""]
        else:
            if mode == "en":
                lines += ["TIẾNG ANH:", ""]
                lines += [c["en"] for c in rows if c.get("en", "").strip()]
            elif mode == "vi":
                lines += ["TIẾNG VIỆT:", ""]
                lines += [c["vi"] for c in rows if c.get("vi", "").strip()]
            else:
                lines += ["TIẾNG ANH:", ""]
                lines += [c["en"] for c in rows if c.get("en", "").strip()]
                lines += ["", "=" * 40, "", "TIẾNG VIỆT:", ""]
                lines += [c["vi"] for c in rows if c.get("vi", "").strip()]
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        messagebox.showinfo("Xong", f"Đã xuất {p} ({len(rows)} câu)")

    def clear_all(self):
        if messagebox.askyesno("Xóa", "Xóa vĩnh viễn toàn bộ hội thoại?"):
            captions.clear()
            for w in (self.txt_en, self.txt_vi):
                w.config(state="normal")
                w.delete("1.0", "end")
                w.config(state="disabled")
            self.set_status("Đã xóa. Dữ liệu đã hủy.")

    def force_finalize(self):
        try:
            if live and pipe_ready:
                fin = live.finalize_fast()
                if fin and fin.get("en"):
                    self.commit_final_en(fin)
                else:
                    messagebox.showinfo("Chốt câu", "Chưa nghe thấy tiếng nói (nguồn im lặng?). Thử KT NGUỒN.")
            else:
                messagebox.showinfo("Chờ chút", "Model chưa tải xong.")
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def check_source(self):
        """KT NGUON: mic -> noi to; loopback -> mo nhac/video cho am thanh phat ra loa."""
        dev, kind, name = self.resolve_source()
        if dev is None:
            messagebox.showerror("Lỗi nguồn", "Không thấy nguồn âm thanh nào. Bấm Quét lại.")
            return
        if kind == "mic":
            self.set_status("KT NGUỒN 3s: hãy NÓI TO vào mic...")
        else:
            self.set_status("KT NGUỒN 3s: hãy MỞ NHẠC/VIDEO (YouTube/Zoom) cho âm thanh phát ra loa...")
        threading.Thread(target=self._check_source_bg, args=(dev, kind, name), daemon=True).start()

    def _check_source_bg(self, dev, kind, name):
        com_init()
        try:
            import numpy as np  # noqa: F401  (giu import de bao loi ro rang neu thieu)
            peaks = []
            with dev.recorder(samplerate=48000, channels=1, blocksize=4096) as rec:
                t0 = time.time()
                while time.time() - t0 < 3:
                    data = rec.record(numframes=4096)
                    peaks.append(float((data.astype("float32") ** 2).mean() ** 0.5))
            peak = max(peaks) * 32768 if peaks else 0
            if peak < 50:
                hint = ("Nói to hơn / chọn mic khác." if kind == "mic"
                        else "Chưa thấy tiếng: hãy PHÁT nhạc/video (âm thanh phải đang kêu ra loa).")
                q_ui.put(("status", f"Nguồn {name}: mức {peak:.0f} ~ im lặng. {hint}"))
            else:
                q_ui.put(("status", f"Nguồn {name}: mức {peak:.0f} → NGHE TỐT. "
                                    "Bấm BẬT NGHE để dịch."))
        except Exception as e:
            log_mic_error("check-source", e)
            q_ui.put(("status", f"Lỗi KT nguồn: {str(e)[:150]}"))

    def test_file(self):
        if not pipe_ready:
            messagebox.showinfo("Chờ chút", "Model chưa tải xong.")
            return
        p = filedialog.askopenfilename(filetypes=[("Audio", "*.wav *.mp3 *.m4a *.flac"), ("All", "*.*")])
        if not p:
            return
        self.set_status(f"Đang dịch file {p} ...")
        threading.Thread(target=self._test_file_bg, args=(p,), daemon=True).start()

    def _test_file_bg(self, p):
        try:
            from src.audio_utils import load_audio_16k
            audio = load_audio_16k(p)
            n = SR * 8
            for i in range(0, len(audio), n):
                seg = audio[i:i + n]
                a = live.sim.asr.transcribe(seg, SR)
                if not a["text"]:
                    continue
                # id ON DINH tu LiveSession -> tuong quan caption van dung
                q_ui.put(("final_en", {"en": a["text"], "asr_ms": a["asr_ms"],
                                       "speaker": "Speaker 1", "id": live.next_id()}))
            q_ui.put(("status", "Dịch file xong."))
        except Exception as e:
            import traceback
            traceback.print_exc()
            q_ui.put(("status", f"Lỗi dịch file: {e}"))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()

"""Desktop ONLY - Nghe hoi thoai EN -> Sub EN (MH1) -> Sub VI (MH2) -> Xuat TXT/SRT.
Chay: python desktop_app_v2.py
Da gon theo huong desktop-realtime: khong server/docker/mobile/TTS/doc/summarize.
Realtime: tiny.en int8 + VinAI greedy beam=1, partial 0.8s, finalize silence 0.8s / max 8s, overlap 0.8s.
"""
import os
os.environ["OFFLINE"] = "1"
os.environ["CONFIDENTIAL"] = "1"
os.environ.setdefault("ASR_MODEL", "tiny.en")
os.environ.setdefault("PARTIAL_EVERY", "0.8")

import time
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

SR = 16000
SPEAK_RMS = 0.008
SIL_S = 0.8
MAX_SEG_S = 8.0
MAX_CAP = 500

# dark professional theme
BG = "#0b1020"
PANEL = "#151d33"
CARD = "#1e293b"
ACCENT = "#0b5cff"
EN_COLOR = "#7dd3fc"
VI_COLOR = "#86efac"
WARN = "#fcd34d"
TXT_FG = "#e5e7eb"

captions = []  # [{en,vi,speaker,t,t_start,t_end,asr_ms,nmt_ms}]
live = None
pipe_ready = False
pipe_error = None

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
    try:
        import ctypes
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass


com_init()


def resample_to_16k(buf, from_sr, to_sr=16000):
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


def nmt_worker():
    """Worker nền: chỉ dịch EN->VI, không bao giờ chặn mic.
    Final dùng accurate=True (beam cao, chuẩn nghĩa nhất), vẫn nhanh vì chạy nền."""
    while True:
        try:
            job = q_nmt.get()
        except Exception:
            continue
        try:
            if live is None:
                continue
            if job[0] != "final":
                continue
            _, idx, en = job
            if not en or not en.strip():
                continue
            t0 = time.time()
            vi, ms, info = live.ctx.translate(en, live.sim.nmt, accurate=True)
            total = (time.time() - t0) * 1000
            q_ui.put(("vi_final", {"idx": idx, "vi": vi,
                                   "scenario": info.get("scenario", "event"),
                                   "nmt_ms": ms, "total_ms": total}))
        except Exception as e:
            log_mic_error("nmt-worker", e)
            continue


def load_models_bg(status_cb):
    global live, pipe_ready, pipe_error
    try:
        import torch
        from src.config import DEFAULT
        from src.asr import FasterWhisperASR
        from src.nmt import NMTTranslator
        from src.live_session import LiveSession
        status_cb("Đang tải model offline (lần đầu 1-2 phút)...")
        use_cuda = torch.cuda.is_available()
        try:
            import os as _os
            _os.cpu_count()
            torch.set_num_threads(max(1, min(_os.cpu_count() or 4, 8)))
            torch.set_num_interop_threads(1)
        except Exception:
            pass
        asr_model = os.getenv("ASR_MODEL") or (DEFAULT.asr_model if use_cuda else "tiny.en")
        beams = 2 if use_cuda else 1
        asr = FasterWhisperASR(asr_model,
                               "cuda" if use_cuda else "cpu",
                               "int8_float16" if use_cuda else "int8",
                               1, "en")
        # partial nhanh: tắt vad_filter trong partial (gate ngoài đã làm), finalize vẫn dùng VAD
        try:
            asr.vad_filter = False
        except Exception:
            pass
        nmt = NMTTranslator(DEFAULT.nmt_model, DEFAULT.nmt_src,
                            DEFAULT.nmt_tgt, num_beams=1,
                            max_len=96)
        engine = "CT2 int8" if getattr(nmt, "ct2", None) is not None else "HF PyTorch"
        live = LiveSession(asr, nmt, None, sr=SR, partial_every_sec=0.8)
        # warm-up: 1s im lặng để chunk đầu không chậm (best-practice whisper_streaming)
        try:
            import numpy as np
            asr.transcribe(np.zeros(SR, dtype=np.float32), SR)
        except Exception:
            pass
        pipe_ready = True
        threading.Thread(target=nmt_worker, daemon=True).start()
        status_cb(f"Sẵn sàng (offline, ASR {asr_model}, NMT {engine} beam live=1/final={nmt.accurate_beams}). Bấm BẬT MIC (F9).")
    except Exception as e:
        import traceback
        traceback.print_exc()
        pipe_error = str(e)
        status_cb(f"Lỗi tải model: {e}")


def open_mic_stream(mic_want=None):
    """Thử đúng mic user chọn, thử samplerate [48000,44100,16000]. Trả (mic, sr)."""
    com_init()
    import soundcard as sc
    if mic_want is None:
        mics = sc.all_microphones(include_loopback=False)
        if not mics:
            raise RuntimeError("Không thấy mic nào.")
        mic_want = mics[0]
    last_err = None
    for sr in (48000, 44100, 16000):
        try:
            # probe mở/đóng nhanh
            with mic_want.recorder(samplerate=sr, channels=1, blocksize=4096):
                pass
            return mic_want, sr
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Mic '{mic_want.name}' không mở được (48000/44100/16000 đều lỗi: {str(last_err)[:150]}). Kiểm tra quyền Microphone Windows + đóng Chrome đang giữ mic.")


class App:
    def __init__(self, root):
        self.root = root
        root.title("Nghe EN → Sub EN + VI (Desktop Offline Realtime)")
        root.geometry("1080x660")
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
        self._build_ui()
        threading.Thread(target=load_models_bg, args=(self.set_status,), daemon=True).start()
        self.root.after(200, self.poll_ui)
        self._bind_keys()

    # ---------- UI ----------
    def _build_ui(self):
        top = tk.Frame(self.root, bg=ACCENT)
        top.pack(fill="x")
        tk.Label(top, text="EN LIVE → VI", bg=ACCENT, fg="white",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=12, pady=8)
        self.btn_mic = tk.Button(top, text="●  BẬT MIC  (F9)", font=("Segoe UI", 11, "bold"),
                                 bg="#22c55e", fg="#04120a", width=18, relief="flat",
                                 command=self.toggle_mic)
        self.btn_mic.pack(side="left", padx=6, pady=6)
        tk.Button(top, text="CHỐT CÂU (Space)", font=("Segoe UI", 10, "bold"),
                  bg=WARN, fg="#04120a", relief="flat",
                  command=self.force_finalize).pack(side="left", padx=4)
        tk.Button(top, text="THỬ FILE", font=("Segoe UI", 10, "bold"),
                  bg=EN_COLOR, fg="#04120a", relief="flat",
                  command=self.test_file).pack(side="left", padx=4)
        tk.Button(top, text="KT MIC", font=("Segoe UI", 10, "bold"),
                  bg="#9fb3ff", fg="#04120a", relief="flat",
                  command=self.check_mic).pack(side="left", padx=4)
        self.lbl_state = tk.Label(top, text="OFFLINE", bg="#04120a", fg=VI_COLOR,
                                  font=("Segoe UI", 9, "bold"), padx=8, pady=4)
        self.lbl_state.pack(side="right", padx=10)

        micbar = tk.Frame(self.root, bg=BG)
        micbar.pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(micbar, text="Mic:", bg=BG, fg="#9fb3ff", font=("Segoe UI", 10)).pack(side="left")
        self.mic_var = tk.StringVar()
        self.mic_box = tk.OptionMenu(micbar, self.mic_var, "")
        self.mic_box.config(bg=CARD, fg="white", relief="flat", highlightthickness=0)
        self.mic_box.pack(side="left", padx=6)
        tk.Button(micbar, text="Quét lại", font=("Segoe UI", 9),
                  bg=CARD, fg="white", relief="flat",
                  command=self.refresh_mics).pack(side="left", padx=4)
        tk.Label(micbar, text="Ngưỡng nói 0.008 • chốt im 0.8s • ép chốt 8s • partial 0.8s",
                 bg=BG, fg="#64748b", font=("Segoe UI", 9)).pack(side="right")
        self.refresh_mics()

        self.status = tk.Label(self.root, text="Đang khởi động...", bg=CARD,
                               fg=WARN, anchor="w", font=("Segoe UI", 10), padx=10, pady=6)
        self.status.pack(fill="x", padx=10, pady=6)

        meterbar = tk.Frame(self.root, bg=BG)
        meterbar.pack(fill="x", padx=10)
        self.meter_canvas = tk.Canvas(meterbar, height=10, bg="#020617", highlightthickness=0)
        self.meter_canvas.pack(fill="x", side="top")
        self.meter = tk.Label(meterbar, text="Mic: ... | ASR: ...", bg=BG,
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
                                 ("XUẤT SRT", "vi", "srt")]:
            tk.Button(bot, text=label, bg="#22c55e", fg="#04120a",
                      font=("Segoe UI", 9, "bold"), relief="flat", padx=8, pady=6,
                      command=lambda m=mode, f=fmt: self.export(m, f)).pack(side="left", padx=4)
        tk.Button(bot, text="XÓA NGAY (Ctrl+L)", bg="#ef4444", fg="white",
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=8, pady=6,
                  command=self.clear_all).pack(side="left", padx=8)
        self.lat = tk.Label(bot, text="", bg=BG, fg="#9fb3ff", font=("Segoe UI", 9))
        self.lat.pack(side="right")

    def _bind_keys(self):
        self.root.bind("<F9>", lambda e: self.toggle_mic())
        self.root.bind("<space>", lambda e: self.force_finalize() if not self._typing() else None)
        self.root.bind("<F5>", lambda e: self.export("both", "txt"))
        self.root.bind("<Control-l>", lambda e: self.clear_all())
        self.root.bind("<Control-L>", lambda e: self.clear_all())

    def _typing(self):
        w = self.root.focus_get()
        return isinstance(w, tk.Text)

    # ---------- status / queue ----------
    def set_status(self, t):
        try:
            q_ui.put_nowait(("status", t))
        except queue.Full:
            pass

    # ---------- mic ----------
    def refresh_mics(self):
        com_init()
        try:
            import soundcard as sc
            names = [m.name for m in sc.all_microphones(include_loopback=False)]
        except Exception as e:
            log_mic_error("refresh-mics", e)
            names = []
        menu = self.mic_box["menu"]
        menu.delete(0, "end")
        if not names:
            names = ["(không thấy mic)"]
        for n in names:
            menu.add_command(label=n, command=lambda v=n: self.mic_var.set(v))
        pick = names[0]
        for n in names:
            if "Array" not in n:
                pick = n
                break
        self.mic_var.set(pick)

    def get_selected_mic(self):
        com_init()
        import soundcard as sc
        want = self.mic_var.get()
        for m in sc.all_microphones(include_loopback=False):
            if m.name == want:
                return m
        ms = sc.all_microphones(include_loopback=False)
        return ms[0] if ms else None

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
        mic = self.get_selected_mic()
        if mic is None:
            messagebox.showerror("Lỗi mic", "Không thấy mic nào. Bấm Quét lại.")
            return
        try:
            mic, sr = open_mic_stream(mic)
        except Exception as e:
            messagebox.showerror("Lỗi mic", str(e))
            self.set_status("Lỗi mic: kiểm tra quyền Microphone Windows + đóng Chrome giữ mic.")
            return
        self._native_sr = sr
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
        self.set_status(f"Đang nghe {mic.name} ({sr}Hz → 16k)... nói tiếng Anh đi.")
        threading.Thread(target=self._sc_loop, args=(mic, sr, gen), daemon=True).start()
        threading.Thread(target=self.mic_loop, args=(gen,), daemon=True).start()

    def _sc_loop(self, mic, sr, gen):
        com_init()
        import numpy as np
        fails = 0
        try:
            with mic.recorder(samplerate=sr, channels=1, blocksize=4096) as rec:
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

    def stop_mic(self):
        self._gen += 1
        self.on = False
        try:
            if live:
                fin = live.finalize_fast()
                if fin and fin.get("en"):
                    q_ui.put(("final_en", fin))
        except Exception:
            pass
        self.btn_mic.config(text="●  BẬT MIC  (F9)", bg="#22c55e", fg="#04120a")
        self.lbl_state.config(text="OFFLINE", fg=VI_COLOR)
        self.set_status("Đã dừng. Bấm XUẤT TXT để lưu, XÓA NGAY để hủy dữ liệu.")

    def mic_loop(self, gen):
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
                ev = live.sim.push_fast(chunk)
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
                # endpointing theo THỜI GIAN (không đếm chunk)
                if rms >= SPEAK_RMS:
                    self._speaking = True
                    self._last_voice = now
                    self.silence_start = None
                else:
                    if self._speaking and self.silence_start is None:
                        self.silence_start = now
                    if self._speaking and self.silence_start and now - self.silence_start >= SIL_S:
                        self.silence_start = None
                        self._speaking = False
                        fin = live.finalize_fast()
                        if fin and fin.get("en"):
                            q_ui.put(("final_en", fin))
                        self._last_commit = now
                    elif self._speaking and now - self._last_commit > MAX_SEG_S:
                        fin = live.finalize_fast()
                        if fin and fin.get("en"):
                            q_ui.put(("final_en", fin))
                        self._last_commit = now
            except Exception as e:
                log_mic_error("mic-loop", e)

    # ---------- UI update ----------
    def poll_ui(self):
        try:
            for _ in range(20):
                kind, data = q_ui.get_nowait()
                if kind == "status":
                    self.status.config(text=data)
                elif kind == "mic_dead":
                    self.on = False
                    self.btn_mic.config(text="●  BẬT MIC  (F9)", bg="#22c55e", fg="#04120a")
                    self.lbl_state.config(text="OFFLINE", fg=VI_COLOR)
                elif kind == "partial_en":
                    self.show_en_live(data.get("en", ""))
                elif kind == "final_en":
                    self.commit_final_en(data)
                elif kind == "vi_final":
                    self.patch_vi_final(data)
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
            if not self.on:
                m = f"Mic: tắt | ASR chạy {self._asr_count} lần, rỗng {self._empty_count} lần"
            elif rms < 0.002:
                m = f"Mic: IM LẶNG (rms={rms:.4f}) — nói to lên! | ASR cuối: {self._last_asr_txt[:50]} ({ago:.0f}s trước)"
            else:
                m = f"Mic: ĐANG NGHE (rms={rms:.4f}) | ASR cuối: {self._last_asr_txt[:50]} ({ago:.0f}s trước)"
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

    def commit_final_en(self, fin):
        en = (fin.get("en") or "").strip()
        if not en:
            return
        spk = fin.get("speaker", "Speaker 1")
        t = time.strftime("%H:%M:%S")
        idx = len(captions)
        if len(captions) >= MAX_CAP:
            captions.pop(0)
            idx -= 1
            self._redraw_vi()
            self._redraw_en()
        captions.append({"en": en, "vi": "", "speaker": spk, "t": t,
                         "t_start": time.time(), "asr_ms": fin.get("asr_ms", 0)})
        for widget in (self.txt_en, self.txt_vi):
            widget.config(state="normal")
            content = widget.get("1.0", "end").splitlines()
            if content and content[-1].startswith("... "):
                widget.delete("end-2l", "end-1l")
            widget.config(state="disabled")
        self._append(self.txt_en, f"[{t}] {en}")
        self._append(self.txt_vi, "(đang dịch...)")
        try:
            q_nmt.put_nowait(("final", idx if idx >= 0 else len(captions) - 1, en))
        except queue.Full:
            pass

    def patch_vi_final(self, d):
        idx, vi = d.get("idx"), d.get("vi", "")
        if idx is None or not (0 <= idx < len(captions)):
            # tìm câu cuối chưa có VI
            for i in range(len(captions) - 1, -1, -1):
                if not captions[i].get("vi"):
                    idx = i
                    break
            else:
                return
        captions[idx]["vi"] = vi
        captions[idx]["nmt_ms"] = d.get("nmt_ms", 0)
        captions[idx]["t_end"] = time.time()
        # cập nhật đúng dòng (không vẽ lại toàn bộ -> không lag)
        try:
            w = self.txt_vi
            w.config(state="normal")
            lines = w.get("1.0", "end").splitlines()
            # dòng idx tương ứng (bỏ dòng live "..." cuối nếu có)
            target = idx + 1  # 1-indexed
            if target <= len(lines):
                w.delete(f"{target}.0", f"{target}.end")
                w.insert(f"{target}.0", f"[{captions[idx]['t']}] {vi}")
            else:
                w.insert("end", f"[{captions[idx]['t']}] {vi}\n")
            w.see("end")
            w.config(state="disabled")
        except Exception:
            self._redraw_vi()
        asr_ms = captions[idx].get("asr_ms", 0) or 0
        nmt_ms = d.get("nmt_ms", 0) or 0
        self.lat.config(text=f"ASR {round(asr_ms)}ms + NMT {round(nmt_ms)}ms | {d.get('scenario','')} | {len(captions)} câu")

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
            w.insert("end", f"[{c['t']}] {c.get('vi') or '(đang dịch...)'}\n")
        w.see("end")
        w.config(state="disabled")

    # ---------- export / clear ----------
    def export(self, mode="both", fmt="txt"):
        rows = [c for c in captions if c.get("en") or c.get("vi")]
        if not rows:
            messagebox.showinfo("Trống", "Chưa có câu hội thoại nào.")
            return
        ext = ".srt" if fmt == "srt" else ".txt"
        p = filedialog.asksaveasfilename(defaultextension=ext,
                                         filetypes=[("Text", "*.txt"), ("SRT", "*.srt"), ("All", "*.*")])
        if not p:
            return

        def srt_ts(sec):
            h = int(sec // 3600); m = int((sec % 3600) // 60)
            s = int(sec % 60); ms = int((sec - int(sec)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        lines = []
        if fmt == "srt":
            t0 = rows[0].get("t_start", time.time())
            idx = 0
            for c in rows:
                txt = c.get("vi") or c.get("en") or ""
                if not txt.strip():
                    continue
                idx += 1
                s = c.get("t_start", t0) - t0
                e = c.get("t_end", c.get("t_start", t0) + 3.0) - t0
                if e <= s:
                    e = s + 3.0
                lines += [str(idx), f"{srt_ts(s)} --> {srt_ts(e)}",
                          f"[{c.get('speaker','Speaker 1')}] {txt}", ""]
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
                    messagebox.showinfo("Chốt câu", "Chưa nghe thấy tiếng nói (mic im lặng?). Thử KT MIC.")
            else:
                messagebox.showinfo("Chờ chút", "Model chưa tải xong.")
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def check_mic(self):
        self.set_status("KT MIC 3s: hãy NÓI TO vào mic...")
        threading.Thread(target=self._check_mic_bg, daemon=True).start()

    def _check_mic_bg(self):
        com_init()
        try:
            import soundcard as sc
            import numpy as np
            mic = self.get_selected_mic()
            if mic is None:
                q_ui.put(("status", "Không thấy mic nào. Bấm Quét lại."))
                return
            name = mic.name
            peaks = []
            with mic.recorder(samplerate=48000, channels=1, blocksize=4096) as rec:
                import time as _t
                t0 = _t.time()
                while _t.time() - t0 < 3:
                    data = rec.record(numframes=4096)
                    peaks.append(float((data.astype("float32") ** 2).mean() ** 0.5))
            peak = max(peaks) * 32768 if peaks else 0
            if peak < 50:
                q_ui.put(("status", f"Mic {name}: mức {peak:.0f} ~ im lặng. Nói to hơn / chọn mic khác."))
            else:
                q_ui.put(("status", f"Mic {name}: mức {peak:.0f} → NGHE TỐT. Bấm BẬT MIC để dịch."))
        except Exception as e:
            log_mic_error("check-mic", e)
            q_ui.put(("status", f"Lỗi KT mic: {str(e)[:150]}"))

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
                fin = {"en": a["text"], "asr_ms": a["asr_ms"], "speaker": "Speaker 1"}
                q_ui.put(("final_en", fin))
            q_ui.put(("status", "Dịch file xong."))
        except Exception as e:
            import traceback
            traceback.print_exc()
            q_ui.put(("status", f"Lỗi dịch file: {e}"))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()

"""App desktop MAT - offline 100%, khong can localhost/browser.
Luong: mic may -> sub EN man hinh 1 -> dich VI man hinh 2 -> xuat TXT + xoa ngay.
Chay: python desktop_app.py
Can: pip install sounddevice (da co trong requirements offline)
Model tai 1 lan: python scripts/download_offline_models.py
"""
import os
os.environ["OFFLINE"] = "1"
os.environ["CONFIDENTIAL"] = "1"
os.environ.setdefault("ASR_MODEL", "tiny.en")
os.environ.setdefault("PARTIAL_EVERY", "0.5")

import time
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

SR = 16000
captions = []  # [{en, vi, speaker, t}]
live = None
pipe_ready = False
pipe_error = None

q_mic = queue.Queue()
q_ui = queue.Queue()
q_nmt = queue.Queue()  # job dich nen: ("live", en) | ("final", idx, en). live duoc phep rot.


def submit_live(en):
    """Gui cau live cho worker dich (worker tu lay ban moi nhat, bo cu)."""
    try:
        q_nmt.put_nowait(("live", en))
    except Exception:
        pass


def nmt_worker():
    """Worker nen: chi dich EN->VI (khong giong doc). Mic khong bao gio bi chan."""
    while True:
        try:
            job = q_nmt.get()
        except Exception:
            continue
        try:
            if live is None:
                continue
            if job[0] == "live":
                _, en = job
                newest = en
                final_waiting = False
                while True:
                    try:
                        nxt = q_nmt.get_nowait()
                    except Exception:
                        break
                    if nxt[0] == "live":
                        newest = nxt[1]
                    else:
                        q_nmt.put(nxt)
                        final_waiting = True
                        break
                if final_waiting:
                    continue  # uu tien cau chot dang cho, bo live cu
                vi, ms = live.sim.nmt.translate(newest)
                q_ui.put(("vi_live", {"en": newest, "vi": vi, "nmt_ms": ms}))
            else:
                _, idx, en = job
                vi, ms, info = live.ctx.translate(en, live.sim.nmt)
                q_ui.put(("vi_final", {"idx": idx, "vi": vi, "scenario": info.get("scenario", "event"),
                                       "audio_vi": None, "nmt_ms": ms, "tts_ms": 0}))
        except Exception as e:
            log_mic_error("nmt-worker", e)
            continue


def resample_to_16k(buf, from_sr, to_sr=16000):
    """Resample mono float32 tu mic native (44100/48000) -> 16k cho Whisper."""
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


def log_mic_error(where, e):
    import traceback
    import datetime
    try:
        with open("mic_error.log", "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}] {where}: {e}\n")
            f.write(traceback.format_exc() + "\n")
    except Exception:
        pass


def com_init():
    """WASAPI (soundcard) bat buoc CoInitialize moi thread. Loi 0x800401F0 = thieu cai nay."""
    try:
        import ctypes
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass


def open_mic_stream(callback):
    """Thu mic: uu tien soundcard WASAPI native (vua test thong), fallback sounddevice.
    Tra (stream_obj, native_sr). stream_obj co .stop()/.close() (sounddevice)
    hoac dict piloting cho soundcard (dung co stop_thread)."""
    # 1. soundcard WASAPI native - vua test REC OK sau khi cap quyen
    try:
        import soundcard as sc
        mics = sc.all_microphones(include_loopback=False)
        if mics:
            return ("soundcard", mics[0]), 48000
    except Exception as e:
        print("[mic] soundcard khong san:", e)
    # 2. fallback sounddevice PortAudio
    import sounddevice as sd
    devs = sd.query_devices()
    cands = []
    for i, d in enumerate(devs):
        if d["max_input_channels"] > 0 and "WDM-KS" not in d["name"]:
            cands.append((i, int(d.get("default_samplerate", 44100)), d["name"]))
    cands = sorted(cands, key=lambda x: 0 if x[0] == sd.default.device[0] else 1)
    errs = []
    for idx, sr, name in cands:
        for ch in (1, 2):
            try:
                s = sd.InputStream(device=idx, samplerate=sr, channels=ch,
                                   dtype="float32", blocksize=4096, callback=callback)
                s.start()
                return s, sr
            except Exception as e:
                errs.append(f"{name} {sr}Hz ch{ch}: {str(e)[:80]}")
                continue
    raise RuntimeError("Mic dang bi khoa.\n- Settings > Privacy > Microphone > Allow desktop apps = On\n- Dong tab Chrome dang giu mic, mo lai app\nChi tiet:\n" + "\n".join(errs[:6]))


def load_models_bg(status_cb):
    global live, pipe_ready, pipe_error
    try:
        import torch
        from src.config import DEFAULT
        from src.asr import FasterWhisperASR
        from src.nmt import NMTTranslator
        from src.tts_offline import OfflineTTSWrapper
        from src.live_session import LiveSession
        status_cb("Dang tai model offline (lan dau 1-2 phut)...")
        use_cuda = torch.cuda.is_available()
        asr_model = DEFAULT.asr_model if use_cuda else "tiny.en"
        beams = 2 if use_cuda else 1
        asr = FasterWhisperASR(asr_model, DEFAULT.asr_device,
                               DEFAULT.asr_compute, DEFAULT.asr_beam,
                               DEFAULT.asr_language)
        nmt = NMTTranslator(DEFAULT.nmt_model, DEFAULT.nmt_src,
                            DEFAULT.nmt_tgt, num_beams=beams)
        # Khong giong doc: don het suc cho chu VI realtime
        tts = None
        live = LiveSession(asr, nmt, tts, sr=SR,
                           partial_every_sec=DEFAULT.partial_every_sec)
        pipe_ready = True
        threading.Thread(target=nmt_worker, daemon=True).start()
        status_cb(f"San sang (offline, {asr_model}, khong giong doc). Bam BAT MIC.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        pipe_error = str(e)
        status_cb(f"Loi tai model: {e}")


def play_wav_bytes(data: bytes):
    """Phat audio VI offline, khong chan UI. Dung soundcard WASAPI (sounddevice out hong theo)."""
    def _play():
        com_init()
        try:
            import io
            import wave
            import numpy as np
            import soundcard as sc
            with wave.open(io.BytesIO(data), "rb") as w:
                n = w.getnframes()
                raw = w.readframes(n)
                sw = w.getsampwidth()
                sr = w.getframerate()
                ch = w.getnchannels()
            dtype = {1: "int8", 2: "int16", 4: "int32"}.get(sw)
            if not dtype:
                return
            arr = np.frombuffer(raw, dtype=dtype).astype("float32")
            if sw == 1:
                arr = (arr - 128) / 128.0
            elif sw == 2:
                arr = arr / 32768.0
            elif sw == 4:
                arr = arr / 2147483648.0
            if ch > 1:
                arr = arr.reshape(-1, ch).mean(axis=1)
            sc.default_speaker().play(arr, samplerate=sr)
        except Exception as e:
            log_mic_error("play", e)
    threading.Thread(target=_play, daemon=True).start()


class App:
    def __init__(self, root):
        self.root = root
        root.title("Hop MAT Offline - Nghe EN -> Sub EN -> Dich VI")
        root.geometry("1000x620")
        root.configure(bg="#0b1020")

        top = tk.Frame(root, bg="#0b5cff")
        top.pack(fill="x")
        self.btn_mic = tk.Button(top, text="BAT MIC", font=("Arial", 12, "bold"),
                                 bg="#22c55e", fg="#04120a", width=14,
                                 command=self.toggle_mic)
        self.btn_mic.pack(side="left", padx=10, pady=8)
        tk.Button(top, text="CHOT CAU", font=("Arial", 10, "bold"),
                  bg="#fcd34d", fg="#04120a",
                  command=self.force_finalize).pack(side="left", padx=4)
        tk.Button(top, text="THU FILE", font=("Arial", 10, "bold"),
                  bg="#7dd3fc", fg="#04120a",
                  command=self.test_file).pack(side="left", padx=4)
        tk.Button(top, text="KT MIC", font=("Arial", 10, "bold"),
                  bg="#9fb3ff", fg="#04120a",
                  command=self.check_mic).pack(side="left", padx=4)
        self.on = False
        self.stream = None
        # Chon mic: may co 2 mic (Array trong + mic moi cam) -> phai chon dung
        micbar = tk.Frame(root, bg="#0b1020")
        micbar.pack(fill="x", padx=8)
        tk.Label(micbar, text="Mic:", bg="#0b1020", fg="#9fb3ff").pack(side="left")
        self.mic_var = tk.StringVar()
        self.mic_box = tk.OptionMenu(micbar, self.mic_var, "")
        self.mic_box.config(bg="#1e293b", fg="white")
        self.mic_box.pack(side="left", padx=4)
        tk.Button(micbar, text="Quet lai", font=("Arial", 9),
                  command=self.refresh_mics).pack(side="left", padx=4)
        self.refresh_mics()

        self.status = tk.Label(root, text="Dang khoi dong...", bg="#1e293b",
                               fg="#fcd34d", anchor="w", font=("Arial", 10))
        self.status.pack(fill="x")
        # Dong ho mic live: biet ngay mic co nghe khong, ASR co chay khong
        self.meter = tk.Label(root, text="Mic: ... | ASR: ...", bg="#0b1020",
                              fg="#9fb3ff", anchor="w", font=("Arial", 9))
        self.meter.pack(fill="x")
        self._last_rms = 0.0
        self._last_asr_txt = ""
        self._last_asr_time = 0.0
        self._asr_count = 0
        self._empty_count = 0

        mid = tk.Frame(root, bg="#0b1020")
        mid.pack(fill="both", expand=True, padx=8, pady=6)

        left = tk.Frame(mid, bg="#151d33")
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        tk.Label(left, text="MAN HINH 1 - NGHE TRUC TIEP (EN)", bg="#151d33",
                 fg="#7dd3fc", font=("Arial", 11, "bold")).pack()
        self.txt_en = tk.Text(left, bg="#0b1020", fg="white", font=("Arial", 11),
                              wrap="word", state="disabled")
        self.txt_en.pack(fill="both", expand=True, padx=6, pady=6)

        right = tk.Frame(mid, bg="#151d33")
        right.pack(side="left", fill="both", expand=True, padx=(4, 0))
        tk.Label(right, text="MAN HINH 2 - DICH TRUC TIEP (VI)", bg="#151d33",
                 fg="#86efac", font=("Arial", 11, "bold")).pack()
        self.txt_vi = tk.Text(right, bg="#0b1020", fg="white", font=("Arial", 11),
                              wrap="word", state="disabled")
        self.txt_vi.pack(fill="both", expand=True, padx=6, pady=6)

        bot = tk.Frame(root, bg="#0b1020")
        bot.pack(fill="x", padx=8, pady=6)
        tk.Label(bot, text="Xong hoi thoai ->", bg="#0b1020",
                 fg="#9fb3ff").pack(side="left")
        for label, mode, fmt in [("XUAT TXT EN-VI", "both", "txt"),
                                 ("XUAT EN", "en", "txt"),
                                 ("XUAT VI", "vi", "txt"),
                                 ("XUAT SRT", "vi", "srt")]:
            tk.Button(bot, text=label, bg="#22c55e", font=("Arial", 9, "bold"),
                      command=lambda m=mode, f=fmt: self.export(m, f)).pack(side="left", padx=4)
        tk.Button(bot, text="XOA NGAY", bg="#ef4444", fg="white",
                  font=("Arial", 9, "bold"), command=self.clear_all).pack(side="left", padx=8)
        self.lat = tk.Label(bot, text="", bg="#0b1020", fg="#9fb3ff")
        self.lat.pack(side="right")

        self.silence = 0
        self._buf_partial_en = ""
        self._buf_partial_vi = ""
        self._live = None
        threading.Thread(target=load_models_bg, args=(self.set_status,), daemon=True).start()
        self.root.after(200, self.poll_ui)

    def set_status(self, t):
        q_ui.put(("status", t))

    def refresh_mics(self):
        """Liet ke mic hien co. Mic moi cam chi hien sau khi quet."""
        try:
            import soundcard as sc
            names = [m.name for m in sc.all_microphones(include_loopback=False)]
        except Exception:
            names = []
        menu = self.mic_box["menu"]
        menu.delete(0, "end")
        if not names:
            names = ["(khong thay mic)"]
        for n in names:
            menu.add_command(label=n, command=lambda v=n: self.mic_var.set(v))
        # uu tien mic moi cam (ten khong phai Array) neu co
        pick = names[0]
        for n in names:
            if "Array" not in n:
                pick = n
                break
        self.mic_var.set(pick)

    def get_selected_mic(self):
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
            messagebox.showinfo("Cho chut", "Model offline chua tai xong, doi 1-2 phut.")
            return
        try:
            import sounddevice as sd
            import numpy as np
        except Exception:
            messagebox.showerror("Thieu mic", "Chua cai sounddevice. Chay: pip install sounddevice")
            return
        # Mic laptop (Senary/MME) chi chiu 44100/48000, xin 16k thang se loi -9999.
        # Mo theo native SR roi resample ve 16k trong callback. Thu tung mic toi khi duoc.
        try:
            import sounddevice as sd
        except Exception:
            messagebox.showerror("Thieu mic", "Chua cai sounddevice. Chay: pip install sounddevice")
            return
        self.on = True
        # xoa queue cu keo sut am cu
        try:
            while True:
                q_mic.get_nowait()
        except Exception:
            pass
        self.btn_mic.config(text="DANG NGHE - BAM DE DUNG", bg="#ef4444", fg="white")

        def cb(indata, frames, t, st):
            if not self.on:
                return
            try:
                mono = indata.mean(axis=1) if indata.ndim > 1 else indata.flatten()
                chunk16 = resample_to_16k(mono.astype("float32"), self._native_sr, SR)
                if len(chunk16):
                    q_mic.put((chunk16 * 32768.0).astype("int16"))
            except Exception:
                pass

        def sc_loop(mic):
            # Thu WASAPI native theo khoi 4096 frame @48k -> resample 16k
            com_init()
            fails = 0
            try:
                with mic.recorder(samplerate=48000, channels=1, blocksize=4096) as rec:
                    while self.on:
                        try:
                            data = rec.record(numframes=4096)
                            fails = 0
                        except Exception as e:
                            fails += 1
                            if fails == 1:
                                log_mic_error("wasapi-record", e)
                            if fails > 20:
                                q_ui.put(("status", f"Loi thu WASAPI lien tuc ({fails}): {str(e)[:120]}. Xem mic_error.log"))
                                break
                            continue
                        if not self.on:
                            break
                        mono = data[:, 0] if data.ndim > 1 else data.flatten()
                        chunk16 = resample_to_16k(mono.astype("float32"), 48000, SR)
                        if len(chunk16):
                            q_mic.put((chunk16 * 32768.0).astype("int16"))
            except Exception as e:
                log_mic_error("wasapi-open", e)
                q_ui.put(("status", f"Loi thu WASAPI: {str(e)[:150]}. Chi tiet trong mic_error.log"))

        try:
            got, self._native_sr = open_mic_stream(cb)
            if isinstance(got, tuple) and got[0] == "soundcard":
                self.stream = None
                self._mic_backend = "soundcard"
                try:
                    self._sc_mic = self.get_selected_mic() or got[1]
                except Exception:
                    self._sc_mic = got[1]
                self.set_status(f"Dang nghe {self._sc_mic.name} (48k -> 16k)... noi tieng Anh di.")
                threading.Thread(target=sc_loop, args=(self._sc_mic,), daemon=True).start()
            else:
                self.stream = got
                self._mic_backend = "portaudio"
                self.set_status(f"Dang nghe (mic {self._native_sr}Hz -> 16k)... noi tieng Anh di.")
        except Exception as e:
            self.on = False
            self.btn_mic.config(text="BAT MIC", bg="#22c55e", fg="#04120a")
            messagebox.showerror("Loi mic", str(e))
            self.set_status("Loi mic: dong Chrome + kiem tra quyen Microphone Windows.")
            return
        threading.Thread(target=self.mic_loop, daemon=True).start()

    def stop_mic(self):
        self.on = False
        try:
            if getattr(self, "stream", None):
                self.stream.stop()
                self.stream.close()
        except Exception:
            pass
        self.stream = None
        # chot cau cuoi (chi ASR, VI tu den sau o worker)
        try:
            if live:
                fin = live.finalize_fast()
                if fin and fin.get("en"):
                    q_ui.put(("final_en", fin))
        except Exception:
            pass
        self.btn_mic.config(text="BAT MIC", bg="#22c55e", fg="#04120a")
        self.set_status("Da dung. Bam XUAT TXT de luu, XOA NGAY de huy du lieu mat.")

    def mic_loop(self):
        import numpy as np
        self._last_commit = time.time()
        self._last_submit = 0.0
        self._submitted_en = ""
        self._speaking = False
        while self.on and live:
            try:
                raw = q_mic.get(timeout=0.5)
            except Exception:
                continue
            chunk = raw.flatten().astype("float32") / 32768.0
            try:
                # Realtime: chi ASR (~0.2s) -> EN hien ngay. NMT chay worker nen.
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
                    en = ev.get("en", "")
                    q_ui.put(("partial_en", {"en": en}))
                    # Khong dich live nua: CPU chi du dich cau chot.
                    # VI hien theo tung cau chot (commit) o worker.
                rms = float((chunk ** 2).mean() ** 0.5) if len(chunk) else 1
                self._last_rms = rms
                if rms >= 0.02:
                    self._speaking = True
                    self.silence = 0
                else:
                    self.silence += 1
                now = time.time()
                # 1. Ngat cau -> chot EN ngay, VI den sau
                if self.silence >= 4:
                    self.silence = 0
                    fin = live.finalize_fast()
                    if fin and fin.get("en"):
                        q_ui.put(("final_en", fin))
                    self._last_commit = now
                    self._speaking = False
                    self._submitted_en = ""
                # 2. Noi lien tuc khong nghi -> tu chot moi 3s (doan ngan -> ASR nhanh)
                elif self._speaking and now - self._last_commit > 3.0:
                    fin = live.finalize_fast()
                    if fin and fin.get("en"):
                        q_ui.put(("final_en", fin))
                    self._last_commit = now
                    self._submitted_en = ""
            except Exception as e:
                print("[mic] loi:", e)

    def poll_ui(self):
        try:
            while True:
                kind, data = q_ui.get_nowait()
                if kind == "status":
                    self.status.config(text=data)
                elif kind == "partial":
                    self.show_partial(data.get("en", ""), data.get("vi", ""))
                elif kind == "final":
                    self.show_final(data)
                elif kind == "partial_en":
                    self.show_en_live(data.get("en", ""))
                elif kind == "vi_live":
                    self.show_vi_live(data.get("en", ""), data.get("vi", ""))
                elif kind == "final_en":
                    self.commit_final_en(data)
                elif kind == "vi_final":
                    self.patch_vi_final(data)
                elif kind == "audio":
                    play_wav_bytes(data)
        except Exception:
            pass
        # Dong ho mic/ASR moi 200ms
        try:
            import time as _t
            rms = getattr(self, "_last_rms", 0.0)
            bars = int(min(20, rms * 400))
            ago = _t.time() - (self._last_asr_time or 0)
            if not getattr(self, "on", False):
                m = f"Mic: tat | ASR chay {self._asr_count} lan, rong {self._empty_count} lan"
            elif rms < 0.002:
                m = f"Mic: {'|' * bars}{' ' * (20 - bars)} rms={rms:.4f} IM LANG - noi to len! | ASR cuoi: {self._last_asr_txt[:40]} ({ago:.0f}s truoc)"
            else:
                m = f"Mic: {'|' * bars}{' ' * (20 - bars)} rms={rms:.4f} DANG NGHE | ASR cuoi: {self._last_asr_txt[:40]} ({ago:.0f}s truoc)"
            self.meter.config(text=m)
        except Exception:
            pass
        self.root.after(200, self.poll_ui)

    def _append(self, widget, text):
        widget.config(state="normal")
        widget.insert("end", text + "\n")
        widget.see("end")
        widget.config(state="disabled")

    def show_partial(self, en, vi):
        # REALTIME: noi den dau hien EN+VI den do, khong cho chot cau.
        # Dong live "... " luon cap nhat + giu de xuat file bat cu luc nao.
        self._live = {"en": en, "vi": vi, "speaker": "Speaker 1",
                      "t": time.strftime("%H:%M:%S")}
        self.status.config(text=f"TRUC TIEP: {en[:80]} ... | Dich: {vi[:80]} ...")
        for widget, txt in ((self.txt_en, en), (self.txt_vi, vi)):
            widget.config(state="normal")
            content = widget.get("1.0", "end").splitlines()
            if content and content[-1].startswith("... "):
                widget.delete("end-2l", "end-1l")
            if txt:
                widget.insert("end", f"... {txt}\n")
                widget.see("end")
            widget.config(state="disabled")

    def show_final(self, fin):
        en, vi = fin.get("en", ""), fin.get("vi", "")
        spk = fin.get("speaker", "Speaker 1")
        t = time.strftime("%H:%M:%S")
        captions.append({"en": en, "vi": vi, "speaker": spk, "t": t})
        self._live = None  # cau live da chot thanh cau that
        # xoa dong partial "... " truoc khi chot cau that
        for widget in (self.txt_en, self.txt_vi):
            widget.config(state="normal")
            content = widget.get("1.0", "end").splitlines()
            if content and content[-1].startswith("... "):
                widget.delete("end-2l", "end-1l")
            widget.config(state="disabled")
        self._append(self.txt_en, f"[{t}][{spk}] {en}")
        self._append(self.txt_vi, f"[{t}][{spk}] {vi}")
        e2e = fin.get("e2e_ms", 0) or 0
        self.lat.config(text=f"E2E {round(e2e)}ms | {fin.get('scenario','')}")
        if fin.get("audio_vi"):
            play_wav_bytes(fin["audio_vi"])

    # ---- Realtime tach NMT: EN hien ngay (~0.5s), VI den sau (worker nen) ----
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
        if not getattr(self, "_live", None):
            self._live = {"en": en, "vi": "", "speaker": "Speaker 1",
                          "t": time.strftime("%H:%M:%S")}
        else:
            self._live["en"] = en
        self._set_live_line(self.txt_en, en)
        self.status.config(text=f"TRUC TIEP: {en[:80]} ...")

    def show_vi_live(self, en, vi):
        if not vi:
            return
        if not getattr(self, "_live", None):
            self._live = {"en": en, "vi": vi, "speaker": "Speaker 1",
                          "t": time.strftime("%H:%M:%S")}
        else:
            self._live["vi"] = vi
            if not self._live.get("en"):
                self._live["en"] = en
        self._set_live_line(self.txt_vi, vi)
        self.status.config(text=f"TRUC TIEP: {en[:60]} ... | Dich: {vi[:60]} ...")

    def commit_final_en(self, fin):
        """Chot cau EN ngay (ASR ~0.2s). VI + giong den sau o worker."""
        en = fin.get("en", "")
        spk = fin.get("speaker", "Speaker 1")
        t = time.strftime("%H:%M:%S")
        idx = len(captions)
        captions.append({"en": en, "vi": "", "speaker": spk, "t": t})
        self._live = None
        for widget in (self.txt_en, self.txt_vi):
            widget.config(state="normal")
            content = widget.get("1.0", "end").splitlines()
            if content and content[-1].startswith("... "):
                widget.delete("end-2l", "end-1l")
            widget.config(state="disabled")
        self._append(self.txt_en, en)
        self._append(self.txt_vi, "(dang dich...)")
        try:
            q_nmt.put_nowait(("final", idx, en))
        except Exception:
            pass

    def patch_vi_final(self, d):
        """Worker dich xong -> dien VI + phat giong, khong chan mic."""
        idx, vi = d.get("idx"), d.get("vi", "")
        if 0 <= idx < len(captions):
            captions[idx]["vi"] = vi
        # ve lai cot VI (captions it, ve lai nhanh). Chi chu, khong thoi gian.
        w = self.txt_vi
        w.config(state="normal")
        w.delete("1.0", "end")
        for c in captions:
            v = c.get("vi") or "(dang dich...)"
            w.insert("end", f"{v}\n")
        if getattr(self, "_live", None) and self._live.get("vi"):
            w.insert("end", f"... {self._live['vi']}\n")
        w.see("end")
        w.config(state="disabled")
        self.lat.config(text=f"VI +{round(d.get('nmt_ms', 0))}ms | {d.get('scenario', '')}")
        if d.get("audio_vi"):
            play_wav_bytes(d["audio_vi"])

    def export(self, mode="both", fmt="txt"):
        rows = list(captions)
        if getattr(self, "_live", None) and self._live.get("en"):
            rows.append(self._live)  # lay ca dong dang noi do de xuat ngay
        if not rows:
            messagebox.showinfo("Trong", "Chua co cau hoi thoai nao.")
            return
        ext = ".srt" if fmt == "srt" else ".txt"
        p = filedialog.asksaveasfilename(defaultextension=ext,
                                         filetypes=[("Text", "*.txt"), ("SRT", "*.srt"), ("All", "*.*")])
        if not p:
            return
        lines = []
        if fmt == "srt":
            t = 0.0
            idx = 0
            for c in rows:
                txt = c["vi"] if mode != "en" else c["en"]
                if not txt.strip():
                    continue
                idx += 1
                lines += [str(idx), f"{self._srt(t)} --> {self._srt(t+3.0)}",
                          f"[{c['speaker']}] {txt}", ""]
                t += 3.4
        else:
            # Xuat chu thuan tuy, khong thoi gian
            if mode == "en":
                lines += ["TIENG ANH:", ""]
                lines += [c["en"] for c in rows if c.get("en", "").strip()]
            elif mode == "vi":
                lines += ["TIENG VIET:", ""]
                lines += [c["vi"] for c in rows if c.get("vi", "").strip()]
            else:
                lines += ["TIENG ANH:", ""]
                lines += [c["en"] for c in rows if c.get("en", "").strip()]
                lines += ["", "=" * 40, "", "TIENG VIET:", ""]
                lines += [c["vi"] for c in rows if c.get("vi", "").strip()]
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        messagebox.showinfo("Xong", f"Da xuat {p}")

    def _srt(self, sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def clear_all(self):
        if messagebox.askyesno("Xoa", "Xoa vinh vien toan bo hoi thoai mat?"):
            captions.clear()
            for w in (self.txt_en, self.txt_vi):
                w.config(state="normal")
                w.delete("1.0", "end")
                w.config(state="disabled")
            self.set_status("Da xoa. Du lieu mat da huy.")

    def force_finalize(self):
        """Nut CHOT CAU: chot EN ngay, VI tu den sau."""
        try:
            if live and pipe_ready:
                fin = live.finalize_fast()
                if fin and fin.get("en"):
                    self.commit_final_en(fin)
                else:
                    messagebox.showinfo("Chot cau", "Chua nghe thay tieng noi (mic im lang?). Thu KT MIC.")
            else:
                messagebox.showinfo("Cho chut", "Model chua tai xong.")
        except Exception as e:
            messagebox.showerror("Loi", str(e))

    def check_mic(self):
        """Do mic DANG CHON 3s bang WASAPI native (soundcard)."""
        com_init()
        try:
            import soundcard as sc
            mic = self.get_selected_mic()
            if mic is None:
                messagebox.showerror("Loi mic", "Khong thay mic nao. Bam Quet lai.")
                return
            msg = f"Mic dang chon: {mic.name}\n\nDang do 3s, hay NOI TO..."
            self.set_status("KT MIC 3s: hay NOI TO vao mic...")
            import time as _t
            import numpy as np
            peaks = []
            with mic.recorder(samplerate=48000, channels=1, blocksize=4096) as rec:
                t0 = _t.time()
                while _t.time() - t0 < 3:
                    data = rec.record(numframes=4096)
                    peaks.append(float((data.astype("float32") ** 2).mean() ** 0.5))
            peak = max(peaks) * 32768 if peaks else 0
            if peak < 50:
                messagebox.showwarning("Mic im lang", f"{msg}\n\nMuc {peak:.0f} ~ im lang. Noi to hon / chon mic khac.")
            else:
                messagebox.showinfo("Mic tot", f"{msg}\n\nMuc {peak:.0f} -> mic NGHE TOT. Bam BAT MIC de dich.")
            self.set_status(f"KT mic xong, muc {peak:.0f}.")
        except Exception as e:
            messagebox.showerror("Loi mic", str(e))

    def test_file(self):
        """THU FILE: bo qua mic, dich thang file wav/mp3 de biet pipeline co chay khong."""
        if not pipe_ready:
            messagebox.showinfo("Cho chut", "Model chua tai xong.")
            return
        p = filedialog.askopenfilename(filetypes=[("Audio", "*.wav *.mp3 *.m4a *.flac"), ("All", "*.*")])
        if not p:
            return
        self.set_status(f"Dang dich file {p} ...")

        def _run():
            try:
                from src.audio_utils import load_audio_16k
                import numpy as np
                audio = load_audio_16k(p)
                # cat 8s / doan cho khoi tran RAM
                n = SR * 8
                for i in range(0, len(audio), n):
                    seg = audio[i:i + n]
                    a = live.sim.asr.transcribe(seg, SR)
                    if not a["text"]:
                        continue
                    vi, _ = live.sim.nmt.translate(a["text"])
                    fin = {"en": a["text"], "vi": vi, "speaker": "Speaker 1",
                           "scenario": "file", "e2e_ms": a["asr_ms"], "audio_vi": None}
                    try:
                        t = live.sim.tts.synth(vi) if live.sim.tts else {"audio": None}
                        fin["audio_vi"] = t["audio"]
                    except Exception:
                        pass
                    q_ui.put(("final", fin))
                q_ui.put(("status", "Dich file xong."))
            except Exception as e:
                import traceback
                traceback.print_exc()
                q_ui.put(("status", f"Loi dich file: {e}"))
        threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()

"""Load test dung DUONG NONG (khong phai poll rong).

Ban cu: moi user tao session rieng roi GET /session/{sid}/captions cua chinh minh
-> luon rong, khong do duoc gi ca.

Ban nay do dung 2 duong that:
- SpeakerUser  : bom PCM 16k int16 qua WS /ws/stream (giong mic that) -> kich hoat
                 ASR + NMT + ghi caption.
- ListenerUser : mo WS /ws/room/{sid} va dem caption nhan duoc -> do fan-out
                 (tinh nang "hang tram nguoi nghe" kieu Saydi Events).

Chay:
    locust -f locustfile.py --host http://localhost
    # hoac headless:
    locust -f locustfile.py --host http://localhost --headless -u 20 -r 5 -t 2m
"""
import threading
import time

import numpy as np
import requests
from locust import User, between, events, task

try:
    import websocket  # websocket-client
except Exception:                                    # pragma: no cover
    websocket = None

SR = 16000
CHUNK = 2048
_SPEECH = (np.random.default_rng(7).standard_normal(SR) * 0.25 * 32768).astype(np.int16)

_shared = {"sid": None, "mode": "translate"}
_lock = threading.Lock()


def ensure_room(host):
    """Tao 1 phong dung chung cho ca bai test (tao 1 lan, co lock)."""
    with _lock:
        if _shared["sid"]:
            return _shared["sid"]
        r = requests.post(f"{host}/session/create",
                          data={"topic": "loadtest", "mode": _shared["mode"]},
                          timeout=10)
        r.raise_for_status()
        _shared["sid"] = r.json()["sid"]
        return _shared["sid"]


def _fire(name, start, ok=True, exc=None, length=0):
    events.request.fire(
        request_type="WS", name=name,
        response_time=(time.time() - start) * 1000,
        response_length=length, exception=exc if not ok else None)


class SpeakerUser(User):
    """Gia lap nguoi noi: bom audio vao /ws/stream."""
    wait_time = between(4, 9)

    def on_start(self):
        try:
            ensure_room(self.host)
        except Exception as e:
            print("[locust] khong tao duoc phong:", e)

    @task
    def speak(self):
        if websocket is None:
            return
        sid = _shared["sid"]
        if not sid:
            return
        url = (self.host.replace("http://", "ws://").replace("https://", "wss://")
               + f"/ws/stream?sid={sid}&partial=1&mode={_shared['mode']}")
        start = time.time()
        try:
            ws = websocket.create_connection(url, timeout=20)
        except Exception as e:
            _fire("ws/stream:connect", start, ok=False, exc=e)
            return
        try:
            # ~2 giay tieng noi, roi frame RONG de server chot cau cuoi
            for i in range(0, len(_SPEECH) - CHUNK, CHUNK):
                ws.send_binary(_SPEECH[i:i + CHUNK].tobytes())
                time.sleep(0.016)                     # ~1x realtime
            ws.send_binary(b"")
            ws.settimeout(25)
            while True:
                try:
                    msg = ws.recv()
                except Exception:
                    break
                if not msg:
                    break
                if isinstance(msg, str) and '"kind": "final"' in msg.replace(" ", " "):
                    break
            _fire("ws/stream:utterance", start, length=len(_SPEECH) * 2)
        except Exception as e:
            _fire("ws/stream:utterance", start, ok=False, exc=e)
        finally:
            try:
                ws.close()
            except Exception:
                pass


class ListenerUser(User):
    """Gia lap nguoi nghe trong phong: mo /ws/room/{sid} va dem caption."""
    wait_time = between(1, 3)

    def on_start(self):
        try:
            ensure_room(self.host)
        except Exception as e:
            print("[locust] khong tao duoc phong:", e)

    @task(3)
    def listen(self):
        if websocket is None:
            return
        sid = _shared["sid"]
        if not sid:
            return
        url = (self.host.replace("http://", "ws://").replace("https://", "wss://")
               + f"/ws/room/{sid}")
        start = time.time()
        got = 0
        try:
            ws = websocket.create_connection(url, timeout=15)
            ws.settimeout(8)
            deadline = time.time() + 8
            while time.time() < deadline:
                msg = ws.recv()
                if not msg:
                    break
                got += 1
            ws.close()
            _fire("ws/room:listen", start, length=got)
        except Exception as e:
            # timeout khi phong im lang la binh thuong -> khong tinh la loi
            if "timed out" in str(e).lower() or "Timeout" in type(e).__name__:
                _fire("ws/room:listen", start, length=got)
            else:
                _fire("ws/room:listen", start, ok=False, exc=e)

    @task(1)
    def poll_captions(self):
        sid = _shared["sid"]
        if not sid:
            return
        start = time.time()
        try:
            r = requests.get(f"{self.host}/session/{sid}/captions?since=0", timeout=10)
            _fire("GET /session/[sid]/captions", start, ok=r.ok,
                  exc=None if r.ok else Exception(f"HTTP {r.status_code}"),
                  length=len(r.content))
        except Exception as e:
            _fire("GET /session/[sid]/captions", start, ok=False, exc=e)

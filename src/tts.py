"""TTS tieng Viet online (Edge-TTS) co cache LRU, timeout va circuit breaker.

Sua loi ban cu:
- Moi lan synth tao MOT ThreadPoolExecutor moi + thread moi -> ton kem, khong gioi han.
- Khong co timeout: mang cham la treo luon luong finalize (va co the treo ca process).
Gio: 1 executor dung lai cho ca phien, `future.result(timeout=...)`, va neu loi/timeout
qua nhieu thi MO MACH (circuit breaker) 60s de khong treo he thong.
"""
import asyncio
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout


class EdgeTTSWrapper:
    def __init__(self, voice="vi-VN-HoaiMyNeural", rate="+10%", cache_size=100,
                 timeout=8.0):
        self.voice, self.rate = voice, rate
        self.cache = OrderedDict()
        self.cache_size = int(cache_size)
        self.timeout = float(timeout)
        self._ex = ThreadPoolExecutor(max_workers=2, thread_name_prefix="edge-tts")
        self._fails = 0
        self._open_until = 0.0
        self.last_error = None

    # ------------------------------------------------------------------ cache
    def _get(self, k):
        if k in self.cache:
            self.cache.move_to_end(k)
            return self.cache[k]
        return None

    def _put(self, k, v):
        self.cache[k] = v
        self.cache.move_to_end(k)
        if len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)

    # ------------------------------------------------------------------ synth
    async def _synth_async(self, text: str):
        import edge_tts
        comm = edge_tts.Communicate(text, self.voice, rate=self.rate)
        chunks = []
        async for c in comm.stream():
            if c["type"] == "audio" and c.get("data"):
                chunks.append(c["data"])
        return b"".join(chunks) if chunks else None

    def _synth_blocking(self, text: str):
        return asyncio.run(self._synth_async(text))

    @property
    def circuit_open(self) -> bool:
        return time.time() < self._open_until

    def synth(self, text: str, out_path: str | None = None):
        text = (text or "").strip()
        if not text:
            return {"audio": None, "tts_ms": 0, "cached": False, "error": None}
        key = f"{self.voice}|{self.rate}|{text}"
        t0 = time.time()
        hit = self._get(key)
        if hit is not None:
            return {"audio": hit, "tts_ms": (time.time() - t0) * 1000,
                    "cached": True, "error": None}
        if self.circuit_open:
            return {"audio": None, "tts_ms": 0, "cached": False,
                    "error": "circuit_open"}

        audio, err = None, None
        try:
            fut = self._ex.submit(self._synth_blocking, text)
            audio = fut.result(timeout=self.timeout)
        except FutureTimeout:
            err = f"timeout>{self.timeout}s"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"

        if err:
            self._fails += 1
            self.last_error = err
            if self._fails >= 3:
                self._open_until = time.time() + 60.0
                self._fails = 0
                print(f"[TTS] edge-tts loi lien tuc ({err}) -> tam tat 60s, "
                      f"van hien chu binh thuong.")
        else:
            self._fails = 0
        if audio:
            self._put(key, audio)
        ms = (time.time() - t0) * 1000
        if audio and out_path:
            with open(out_path, "wb") as f:
                f.write(audio)
        return {"audio": audio, "tts_ms": ms, "cached": False, "error": err}

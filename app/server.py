"""FastAPI realtime server EN -> VI (kieu Saydi, CHI 1 cap ngon ngu).

Endpoints:
- WS  /ws/stream                  : mic/tab audio -> partial + final (EN + VI)
- WS  /ws/room/{sid}              : nguoi nghe nhan caption realtime (khong poll)
- GET /m , GET /room/{sid}        : PWA mobile + trang nguoi nghe (QR join)
- POST /session/create            : tao phong (topic, pin, mode, scenario, keywords, terms)
- POST /session/{sid}/context     : doi ngu canh/thuat ngu giua cuoc hop
- GET /session/{sid}/captions     : doc caption (PIN)
- GET /session/{sid}/export       : TXT / SRT / VTT (thoi gian THAT)
- GET /session/{sid}/qr.png       : ma QR de moi nguoi vao phong
- POST /session/{sid}/summary     : tom tat + action items
- DELETE /session/{sid}           : xoa ngay (che do mat)
- POST /translate_file, /doctranslate, /summarize
- GET /health, /metrics

Sua loi ban cu:
1. ASR/NMT/TTS chay DONG BO trong coroutine -> chan event loop (1 client noi la ca
   server dung). Gio day sang threadpool qua `run_in_threadpool` + lock rieng cho
   tung model (ASR va NMT chay song song duoc).
2. Chot cau theo SO CHUNK (`silence >= 4`) -> mobile (buffer ~85ms) chot sau 0.34s,
   desktop sau ~1s. Gio endpointing theo GIAY tu `config.final_silence_sec`.
3. `os.environ.pop` API key giua request -> tat LLM vinh vien cho ca process.
4. `/translate_file`, `/doctranslate` khong kiem tra model da tai xong -> 500.
5. `session_qr` chi tra link; gio tra PNG that (neu co thu vien).
6. WebSocketDisconnect bi `except Exception` -> in traceback cho moi lan dong tab.
7. `/doctranslate` de lai file dich trong temp (trai voi tuyen bo "mat/tu xoa").
"""
import asyncio
import base64
import os
import tempfile
import threading
import time
from collections import deque
from contextlib import asynccontextmanager

import numpy as np
from fastapi import (FastAPI, Form, Header, HTTPException, Request, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, Response)
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from src.config import DEFAULT

CONFIDENTIAL = DEFAULT.confidential
APP_START = time.time()

STATS = {
    "ws_stream": 0, "ws_room": 0, "captions": 0, "sessions": 0,
    "asr_ms": deque(maxlen=200), "nmt_ms": deque(maxlen=200),
    "e2e_ms": deque(maxlen=200), "errors": 0,
}

app = FastAPI(
    title="EN-VI Streaming Speech Translation",
    docs_url=None if CONFIDENTIAL else "/docs",
    openapi_url=None if CONFIDENTIAL else "/openapi.json",
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOBILE = os.path.join(BASE, "static", "mobile")
ROOM = os.path.join(BASE, "static", "room")
@app.get("/static/mobile/sw.js")
def service_worker():
    """Service worker can header `Service-Worker-Allowed` moi co scope toan site.

    Khong co header nay, trinh duyet gioi han scope vao /static/mobile/ -> SW khong
    bao gio bat duoc trang /m. Route nay PHAI khai bao TRUOC mount ben duoi, vi
    Starlette khop route theo thu tu dang ky.
    """
    p = os.path.join(MOBILE, "sw.js")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="sw.js chua co")
    return FileResponse(p, media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/",
                                 "Cache-Control": "no-cache"})


if os.path.isdir(MOBILE):
    app.mount("/static/mobile", StaticFiles(directory=MOBILE, html=True), name="mobile")
if os.path.isdir(ROOM):
    app.mount("/static/room", StaticFiles(directory=ROOM, html=True), name="room")


# ====================================================================== pipeline
class Pipeline:
    """Bo model dung chung cho moi phien (ASR + NMT + TTS tuy chon)."""

    def __init__(self):
        import torch
        from src.asr import FasterWhisperASR
        from src.nmt import NMTTranslator

        self.cfg = DEFAULT
        self.use_cuda = torch.cuda.is_available()
        asr_model = DEFAULT.resolve_asr_model(self.use_cuda)
        self.asr = FasterWhisperASR(
            asr_model, DEFAULT.asr_device, DEFAULT.resolve_compute(self.use_cuda),
            DEFAULT.asr_beam, DEFAULT.asr_language,
            vad_filter=DEFAULT.asr_vad_filter, gate_rms=DEFAULT.asr_gate_rms)
        self.nmt = NMTTranslator(
            DEFAULT.nmt_model, DEFAULT.nmt_src, DEFAULT.nmt_tgt,
            num_beams=DEFAULT.nmt_live_beams, max_len=DEFAULT.nmt_max_len,
            accurate_beams=DEFAULT.resolve_final_beams(self.use_cuda),
            cache_size=DEFAULT.nmt_cache_size, ct2_path=DEFAULT.ct2_dir)
        self.tts = self._build_tts()

    def _build_tts(self):
        if DEFAULT.tts_engine == "offline":
            from src.tts_offline import OfflineTTSWrapper
            return OfflineTTSWrapper(DEFAULT.piper_model, DEFAULT.tts_cache_size)
        try:
            from src.tts import EdgeTTSWrapper
            return EdgeTTSWrapper(DEFAULT.tts_voice, DEFAULT.tts_rate,
                                  DEFAULT.tts_cache_size, DEFAULT.tts_timeout_sec)
        except Exception as e:
            print("[server] Edge TTS khong dung duoc, chuyen offline:", e)
            from src.tts_offline import OfflineTTSWrapper
            return OfflineTTSWrapper(DEFAULT.piper_model, DEFAULT.tts_cache_size)

    def info(self):
        return {"asr": DEFAULT.resolve_asr_model(self.use_cuda),
                "cuda": self.use_cuda,
                "nmt": self.nmt.stats(),
                "tts": DEFAULT.tts_engine,
                "mode": DEFAULT.mode}


_pipe = None
_pipe_error = None
_pipe_loading = False
_pipe_lock = threading.Lock()

# lock rieng tung model: ASR va NMT chay song song, khong chan nhau
ASR_LOCK = threading.Lock()
NMT_LOCK = threading.Lock()
TTS_LOCK = threading.Lock()

# registry phien dang chay de doi ngu canh giua cuoc hop
LIVE_SESSIONS = {}
LIVE_LOCK = threading.Lock()


def _load_pipe_sync():
    global _pipe, _pipe_error, _pipe_loading
    with _pipe_lock:
        if _pipe is not None or _pipe_loading:
            return _pipe
        _pipe_loading = True
    try:
        p = Pipeline()
        with _pipe_lock:
            _pipe = p
            _pipe_error = None
        return p
    except Exception as e:
        import traceback
        traceback.print_exc()
        with _pipe_lock:
            _pipe_error = f"{type(e).__name__}: {e}"
        return None
    finally:
        with _pipe_lock:
            _pipe_loading = False


async def ensure_pipe(ws: WebSocket | None = None, timeout_sec: float = 600.0):
    """Tra ve Pipeline hoac None. Gui trang thai cho client trong luc cho."""
    p = _pipe
    if p is not None:
        return p
    if ws is not None:
        await ws.send_json({"kind": "status", "status": "loading",
                            "msg": "Model dang tai (Whisper + VinAI, 1-2 phut lan dau). "
                                   "Giu ket noi..."})
    p = await run_in_threadpool(_load_pipe_sync)
    if p is None and _pipe_loading:
        waited = 0.0
        while waited < timeout_sec and _pipe is None:
            await asyncio.sleep(2.0)
            waited += 2.0
        p = _pipe
    return p


async def _infer(lock, fn, *args, **kwargs):
    """Chay inference trong threadpool, serialize theo tung model."""
    def _call():
        with lock:
            return fn(*args, **kwargs)
    return await run_in_threadpool(_call)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async def _warm():
        await run_in_threadpool(_load_pipe_sync)
    asyncio.create_task(_warm())

    async def _sweeper():
        from src import rooms
        while True:
            await asyncio.sleep(300)
            try:
                rooms.sweep_expired()
                # don ngu canh cua phong da chet (tranh ro ri bo nho)
                with LIVE_LOCK:
                    for k in list(LIVE_CONTEXT):
                        if rooms.get_session(k) is None:
                            LIVE_CONTEXT.pop(k, None)
            except Exception:
                pass
    sweep_task = asyncio.create_task(_sweeper())
    yield
    sweep_task.cancel()


app.router.lifespan_context = lifespan


# ====================================================================== helpers
def _pin(request: Request, x_room_pin: str | None = None) -> str:
    return ((x_room_pin or request.query_params.get("pin") or "") or "").strip()


def _require_room(sid: str, pin: str):
    from src import rooms
    if rooms.get_session(sid) is None:
        raise HTTPException(status_code=404, detail=f"Khong tim thay phong {sid}")
    if not rooms.check_pin(sid, pin):
        raise HTTPException(status_code=403, detail="Sai PIN phong hop mat")


def _pct(vals, p):
    if not vals:
        return 0.0
    a = sorted(vals)
    i = min(len(a) - 1, max(0, int(round((p / 100.0) * (len(a) - 1)))))
    return float(a[i])


# ====================================================================== meta
@app.get("/health")
def health():
    from src import rooms
    p = _pipe
    return {
        "loaded": p is not None,
        "loading": _pipe_loading,
        "error": _pipe_error,
        "offline": DEFAULT.offline,
        "confidential": CONFIDENTIAL,
        "tts": DEFAULT.tts_engine,
        "asr": (p.info()["asr"] if p else DEFAULT.resolve_asr_model(False)),
        "mode": DEFAULT.mode,
        "partial_every": DEFAULT.partial_every_sec,
        "final_silence": DEFAULT.final_silence_sec,
        "glossary_terms": DEFAULT.glossary_max_terms,
        "rooms": len(rooms.SESSIONS),
        "uptime_sec": round(time.time() - APP_START, 1),
    }


@app.get("/metrics")
def metrics():
    return {
        "uptime_sec": round(time.time() - APP_START, 1),
        "ws_stream": STATS["ws_stream"], "ws_room": STATS["ws_room"],
        "captions": STATS["captions"], "sessions": STATS["sessions"],
        "errors": STATS["errors"],
        "latency_ms": {
            "asr_p50": _pct(STATS["asr_ms"], 50), "asr_p90": _pct(STATS["asr_ms"], 90),
            "nmt_p50": _pct(STATS["nmt_ms"], 50), "nmt_p90": _pct(STATS["nmt_ms"], 90),
            "e2e_p50": _pct(STATS["e2e_ms"], 50), "e2e_p90": _pct(STATS["e2e_ms"], 90),
            "samples": len(STATS["e2e_ms"]),
        },
        "target_e2e_sec": DEFAULT.target_e2e_sec,
    }


# ====================================================================== pages
@app.get("/m", response_class=HTMLResponse)
def mobile():
    p = os.path.join(MOBILE, "index.html")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>Mobile PWA chua co</h1>", status_code=404)


@app.get("/room/{sid}", response_class=HTMLResponse)
def room_page(sid: str):
    p = os.path.join(ROOM, "index.html")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>Trang phong chua co</h1>", status_code=404)


# ====================================================================== sessions
@app.post("/session/create")
def session_create(topic: str = Form(""), host: str = Form(""),
                   pin: str = Form(""), mode: str = Form(""),
                   scenario: str = Form("event"), keywords: str = Form(""),
                   details: str = Form(""), terms: str = Form("")):
    from src import rooms
    sid = rooms.create_session(topic, pin=pin, mode=mode or DEFAULT.mode,
                               host=host or DEFAULT.host)
    s = rooms.get_session(sid)
    # ngu canh ban dau (Saydi: Scenario Gallery + Meeting Details & Keywords + Dictionary)
    ctx = {"scenario": scenario or "event", "keywords": keywords or "",
           "details": details or "", "terms": terms or ""}
    with LIVE_LOCK:
        LIVE_CONTEXT[sid] = ctx
    STATS["sessions"] += 1
    return {"sid": sid, "link": rooms.session_link(sid, host or DEFAULT.host),
            "qr": rooms.session_qr(sid, host or DEFAULT.host),
            "locked": bool((pin or "").strip()),
            "mode": s.get("mode", DEFAULT.mode) if s else DEFAULT.mode,
            "scenario": scenario or "event"}


# ngu canh cho phien (nap khi bat dau + doi giua cuoc hop)
LIVE_CONTEXT = {}


def _parse_terms(terms) -> dict:
    """'api=API, latency=độ trễ' hoac dict -> dict."""
    if not terms:
        return {}
    if isinstance(terms, dict):
        return {str(k): str(v) for k, v in terms.items() if k and v}
    out = {}
    for chunk in str(terms).replace("\n", ",").split(","):
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
    return out


def _apply_context(live, sid: str, payload: dict | None = None):
    """Nap ngu canh vao LiveSession dang chay (hoac lay tu LIVE_CONTEXT)."""
    ctx = dict(LIVE_CONTEXT.get(sid, {}))
    if payload:
        ctx.update({k: v for k, v in payload.items() if v is not None})
        LIVE_CONTEXT[sid] = ctx
    if not ctx:
        return None
    try:
        return live.set_context(
            scenario=ctx.get("scenario") or None,
            details=ctx.get("details") if ctx.get("details") is not None else None,
            keywords=(ctx.get("keywords") if ctx.get("keywords") is not None else None),
            terms=_parse_terms(ctx.get("terms")),
            replace_terms=True)
    except ValueError as e:
        return {"error": str(e)}


@app.post("/session/{sid}/context")
async def session_context(sid: str, request: Request,
                          x_room_pin: str | None = Header(None)):
    from src import rooms
    _require_room(sid, _pin(request, x_room_pin))
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    with LIVE_LOCK:
        live = LIVE_SESSIONS.get(sid)
    if live is not None:
        return _apply_context(live, sid, body)
    ctx = dict(LIVE_CONTEXT.get(sid, {}))
    ctx.update({k: v for k, v in body.items() if v is not None})
    LIVE_CONTEXT[sid] = ctx
    return {"saved": True, "applies_when_stream_starts": True, **ctx}


@app.get("/session/{sid}/captions")
def session_caps(sid: str, request: Request, since: int = 0,
                 x_room_pin: str | None = Header(None)):
    from src import rooms
    _require_room(sid, _pin(request, x_room_pin))
    s = rooms.get_session(sid)
    caps = rooms.get_captions(sid, since)
    return {"captions": caps,
            "n_speakers": s.get("n_speakers", 1),
            "scenario": s.get("scenario", "event"),
            "mode": s.get("mode", DEFAULT.mode),
            "ended": bool(s.get("ended", False)),
            "total": s.get("n", len(caps))}


@app.get("/session/{sid}/export")
def session_export(sid: str, request: Request, format: str = "txt",
                   mode: str = "both", x_room_pin: str | None = Header(None)):
    from src import rooms
    _require_room(sid, _pin(request, x_room_pin))
    fmt = (format or "txt").lower()
    md = (mode or "both").lower()
    if fmt == "srt":
        content = rooms.export_session_srt(sid, lang="vi") or ""
        fname, media = f"hoithoai_{sid}_vi.srt", "application/x-subrip"
    elif fmt == "vtt":
        content = rooms.export_session_vtt(sid, lang="vi") or ""
        fname, media = f"hoithoai_{sid}_vi.vtt", "text/vtt"
    else:
        if md not in ("both", "en", "vi"):
            md = "both"
        content = rooms.export_session_txt(sid, mode=md) or ""
        fname, media = f"hoithoai_{sid}_{md}.txt", "text/plain; charset=utf-8"
    if not content:
        content = "(Chua co cau hoi thoai nao)"
    with tempfile.NamedTemporaryFile(delete=False, suffix="_" + fname, mode="w",
                                     encoding="utf-8") as tmp:
        tmp.write(content)
        path = tmp.name
    # che do mat: xoa file tam ngay sau khi gui xong
    from starlette.background import BackgroundTask
    return FileResponse(path, filename=fname, media_type=media,
                        background=BackgroundTask(lambda: os.path.exists(path) and os.remove(path)))


@app.get("/session/{sid}/qr.png")
def session_qr_png(sid: str):
    from src import rooms
    if rooms.get_session(sid) is None:
        raise HTTPException(status_code=404, detail="Khong tim thay phong")
    png = rooms.session_qr_png(sid, DEFAULT.host)
    if not png:
        raise HTTPException(status_code=503,
                            detail="Thieu thu vien qrcode (pip install qrcode[pil])")
    return Response(content=png, media_type="image/png")


@app.post("/session/{sid}/summary")
async def session_summary(sid: str, request: Request,
                          x_room_pin: str | None = Header(None)):
    from src import rooms
    _require_room(sid, _pin(request, x_room_pin))
    res = await run_in_threadpool(rooms.build_minutes, sid)
    if res is None:
        raise HTTPException(status_code=404, detail="Khong tim thay phong")
    return res


@app.delete("/session/{sid}")
def session_delete(sid: str, request: Request,
                   x_room_pin: str | None = Header(None)):
    from src import rooms
    _require_room(sid, _pin(request, x_room_pin))
    rooms.delete_session(sid)
    with LIVE_LOCK:
        LIVE_SESSIONS.pop(sid, None)
        LIVE_CONTEXT.pop(sid, None)
    return {"deleted": sid}


# ====================================================================== file jobs
@app.post("/translate_file")
async def translate_file(f: UploadFile):
    from src.metrics import latency_stats
    pipe = await ensure_pipe()
    if pipe is None:
        raise HTTPException(status_code=503,
                            detail=f"Model chua tai xong: {_pipe_error}")
    with tempfile.NamedTemporaryFile(delete=False, suffix="_" + (f.filename or "a.wav")) as tmp:
        tmp.write(await f.read())
        path = tmp.name
    try:
        from src.pipeline import CascadedPipeline
        from src.context_engine import ContextEngine
        ctx = ContextEngine(DEFAULT.mode and "event")
        pipe2 = CascadedPipeline(pipe.asr, pipe.nmt, pipe.tts,
                                 DEFAULT.sample_rate, DEFAULT.target_e2e_sec)
        res = await run_in_threadpool(pipe2.process_file, path)
        out = [{k: r[k] for k in ("seg", "start", "end", "en", "vi", "asr_ms",
                                  "nmt_ms", "tts_ms", "e2e_ms", "realtime_ok") if k in r}
               for r in res]
        return {"segments": out, "stats": latency_stats(res),
                "scenario": ctx.scenario}
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


@app.post("/doctranslate")
async def doctranslate(f: UploadFile):
    pipe = await ensure_pipe()
    if pipe is None:
        raise HTTPException(status_code=503, detail=f"Model chua tai xong: {_pipe_error}")
    from src.doctranslate import translate_doc
    name = f.filename or "doc.txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix="_" + name) as tmp:
        tmp.write(await f.read())
        path = tmp.name
    out = path + ".vi" + os.path.splitext(name)[1]
    try:
        await run_in_threadpool(translate_doc, path, out, pipe.nmt)
        from starlette.background import BackgroundTask

        def _cleanup():
            for p in (path, out):
                try:
                    os.remove(p)
                except Exception:
                    pass
        return FileResponse(out, filename="translated_" + name,
                            background=BackgroundTask(_cleanup))
    except Exception as e:
        for p in (path, out):
            try:
                os.remove(p)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summarize")
async def summarize(body: dict):
    """Tom tat offline/LLM. KHONG mutate os.environ nua (loi cu tat LLM ca process)."""
    from src.summarizer import summarize as _sum
    text = (body or {}).get("vi_text", "") or (body or {}).get("text", "")
    return await run_in_threadpool(_sum, text)


# ====================================================================== websockets
@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    from src import rooms
    from src.live_session import LiveSession

    await ws.accept()
    qp = dict(ws.query_params)
    sid = (qp.get("sid") or "").strip() or None
    pin = (qp.get("pin") or "").strip()
    mode = (qp.get("mode") or DEFAULT.mode).strip().lower()
    if mode not in ("translate", "transcribe"):
        mode = DEFAULT.mode
    want_partial = qp.get("partial", "1") == "1"
    want_tts = qp.get("tts", "0") == "1"
    want_vi = (mode == "translate")

    session = None
    if sid:
        session = rooms.get_session(sid)
        if session is None:
            await ws.send_json({"kind": "status", "status": "error",
                                "msg": f"Khong tim thay phong {sid}"})
            await ws.close(code=4404)
            return
        if not rooms.check_pin(sid, pin):
            await ws.send_json({"kind": "status", "status": "error",
                                "msg": "Sai PIN phong hop mat"})
            await ws.close(code=4403)
            return
        mode = session.get("mode", mode)
        want_vi = (mode == "translate")

    pipe = await ensure_pipe(ws)
    if pipe is None:
        await ws.send_json({"kind": "status", "status": "error",
                            "msg": f"Khong tai duoc model: {_pipe_error}"})
        await ws.close()
        return

    tts = pipe.tts if (want_tts and want_vi) else None
    live = LiveSession(pipe.asr, pipe.nmt, tts, sr=DEFAULT.sample_rate, sid=sid,
                       mode=mode)
    _apply_context(live, sid)
    if sid:
        with LIVE_LOCK:
            LIVE_SESSIONS[sid] = live
    STATS["ws_stream"] += 1
    await ws.send_json({"kind": "status", "status": "ready",
                        "msg": f"San sang (che do {mode}). Hay noi tieng Anh."})

    silence_since = None
    speaking = False
    seg_start = time.time()

    async def do_finalize():
        nonlocal speaking, silence_since, seg_start
        speaking = False
        silence_since = None
        t_end = time.time()
        fin = await _infer(ASR_LOCK, live.finalize_text)
        if not fin:
            seg_start = time.time()
            return
        fin["t_start"] = seg_start
        fin["t_end"] = t_end
        seg_start = time.time()
        t0 = time.time()
        if want_vi:
            vi, nmt_ms, info = await _infer(NMT_LOCK, live.translate, fin["en"], True)
            fin["vi"], fin["nmt_ms"] = vi, nmt_ms
            fin["scenario"] = info.get("scenario", fin.get("scenario"))
            fin["numbers_missing"] = info.get("numbers_missing", [])
        if tts is not None and fin.get("vi"):
            audio, tts_ms = await _infer(TTS_LOCK, live.speak, fin["vi"])
            fin["audio_vi"], fin["tts_ms"] = audio, tts_ms
        fin["e2e_ms"] = float(fin.get("asr_ms", 0.0)) + (time.time() - t0) * 1000
        STATS["asr_ms"].append(float(fin.get("asr_ms", 0.0)))
        STATS["nmt_ms"].append(float(fin.get("nmt_ms", 0.0)))
        STATS["e2e_ms"].append(float(fin.get("e2e_ms", 0.0)))
        payload = _encode_fin(fin)
        await ws.send_json(payload)
        if sid:
            cap = rooms.add_caption(
                sid, fin["en"], fin.get("vi"), fin.get("speaker", "Speaker 1"),
                t_start=fin["t_start"], t_end=fin["t_end"],
                asr_ms=fin.get("asr_ms", 0), nmt_ms=fin.get("nmt_ms", 0),
                e2e_ms=fin.get("e2e_ms", 0), scenario=fin.get("scenario"))
            if cap:
                STATS["captions"] += 1

    try:
        while True:
            raw = await ws.receive_bytes()
            if len(raw) == 0:                 # client bao DUNG -> chot cau cuoi
                await do_finalize()
                continue
            chunk = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float((chunk ** 2).mean() ** 0.5) if len(chunk) else 1.0
            now = time.time()
            if rms >= DEFAULT.speak_rms:
                speaking = True
                silence_since = None
            else:
                if speaking and silence_since is None:
                    silence_since = now

            if want_partial:
                ev = await _infer(ASR_LOCK, live.sim.push_fast, chunk)
                if ev:
                    if want_vi:
                        vi, nmt_ms = await _infer(NMT_LOCK, live.sim.nmt.translate, ev["en"])
                        ev["vi"], ev["nmt_ms"] = vi, nmt_ms
                    ev["audio_vi"] = None
                    await ws.send_json(ev)

            # endpointing theo GIAY (khong dem chunk -> dung cho moi thiet bi)
            if speaking and silence_since and now - silence_since >= DEFAULT.final_silence_sec:
                await do_finalize()
            elif speaking and now - seg_start > DEFAULT.max_seg_sec:
                await do_finalize()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        STATS["errors"] += 1
        import traceback
        traceback.print_exc()
        try:
            await ws.send_json({"kind": "status", "status": "error", "msg": str(e)})
        except Exception:
            pass
    finally:
        try:
            await do_finalize()               # khong mat cau cuoi khi client ngat
        except Exception:
            pass
        if sid:
            with LIVE_LOCK:
                LIVE_SESSIONS.pop(sid, None)
        try:
            await ws.close()
        except Exception:
            pass


def _encode_fin(fin: dict) -> dict:
    """Encode final cho WS. Tu nhan mp3 (Edge online) hay wav (offline)."""
    out = {}
    for k in ("kind", "id", "en", "vi", "speaker", "scenario", "n_speakers",
              "asr_ms", "nmt_ms", "tts_ms", "e2e_ms", "numbers_missing", "mode"):
        out[k] = fin.get(k)
    v = fin.get("audio_vi")
    if v:
        out["audio_vi"] = base64.b64encode(v).decode()
        out["audio_mime"] = "audio/wav" if v[:4] == b"RIFF" else "audio/mp3"
    else:
        out["audio_vi"] = None
        out["audio_mime"] = "audio/mp3"
    out["kind"] = "final"
    return out


@app.websocket("/ws/room/{sid}")
async def ws_room(ws: WebSocket, sid: str):
    """Nguoi nghe: nhan caption realtime qua kenh thong bao (khong poll 1s/lan)."""
    from src import rooms
    await ws.accept()
    pin = (ws.query_params.get("pin") or "").strip()
    session = rooms.get_session(sid)
    if session is None:
        await ws.send_json({"kind": "status", "status": "error",
                            "msg": f"Khong tim thay phong {sid}"})
        await ws.close(code=4404)
        return
    if not rooms.check_pin(sid, pin):
        await ws.send_json({"kind": "status", "status": "error",
                            "msg": "Sai PIN phong hop mat"})
        await ws.close(code=4403)
        return

    STATS["ws_room"] += 1
    caps = rooms.get_captions(sid, 0)
    await ws.send_json({"kind": "snapshot", "captions": caps,
                        "mode": session.get("mode", DEFAULT.mode),
                        "scenario": session.get("scenario", "event"),
                        "n_speakers": session.get("n_speakers", 1),
                        "total": session.get("n", len(caps))})

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=500)

    def _cb(cap):
        try:
            loop.call_soon_threadsafe(q.put_nowait, cap)
        except Exception:
            pass

    # Redis pub/sub neu co (nhieu replica), khong thi dung notify trong process.
    # Chi chon MOT duong de khong bi trung caption.
    unsub = rooms.subscribe_redis(sid, _cb)
    if unsub is None:
        rooms.subscribe(sid, _cb)
        unsub = lambda: rooms.unsubscribe(sid, _cb)  # noqa: E731

    async def _sender():
        while True:
            try:
                cap = await asyncio.wait_for(q.get(), timeout=20.0)
                await ws.send_json({"kind": "caption", **cap})
            except asyncio.TimeoutError:
                await ws.send_json({"kind": "ping"})

    async def _reader():
        try:
            while True:
                msg = await ws.receive_text()
                if (msg or "").strip().lower() == "close":
                    return
                if (msg or "").strip().lower() == "ping":
                    await ws.send_json({"kind": "pong"})
        except WebSocketDisconnect:
            # client dong tab binh thuong: khong phai loi, khong in traceback
            return
        except Exception:
            return

    sender = asyncio.create_task(_sender())
    reader = asyncio.create_task(_reader())
    try:
        done, pending = await asyncio.wait({sender, reader},
                                           return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        pass
    except Exception:
        STATS["errors"] += 1
    finally:
        try:
            unsub()
        except Exception:
            pass
        for t in (sender, reader):
            if not t.done():
                t.cancel()
        # thu hoi exception cua task da huy -> khong con
        # "Task exception was never retrieved: WebSocketDisconnect" khi client ngat
        await asyncio.gather(sender, reader, return_exceptions=True)
        try:
            await ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

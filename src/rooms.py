"""Phong hop / phien + chia se caption (kieu Saydi Events), CHI EN -> VI.

Che do luu:
- 1 worker (mac dinh): luu RAM
- nhieu worker: tu dung Redis neu co REDIS_URL

Sua loi ban cu:
1. `push_caption` doc-sua-ghi CA blob JSON -> voi nhieu worker la MAT caption
   (lost update). Gio caption la Redis LIST (RPUSH + LTRIM), meta la 1 key rieng.
2. `export_session_srt` bia timestamp (moi cue 3.0s noi tiep) -> phu de lech hoan toan.
   Gio dung `t_start`/`t_end`/`ts` that cua tung cau.
3. PIN so sanh bang `==` (khong constant-time) va luu plaintext. Gio luu hash+salt
   va so sanh bang `hmac.compare_digest`.
4. `session_qr` chi tra ve LINK (khong phai QR). Gio tra PNG that (neu co thu vien),
   kem fallback link de khong vo he thong.
5. Phong RAM khong bao gio het han -> phinh RAM. Gio co `sweep_expired()`.
6. Them kenh thong bao (`subscribe`/`unsubscribe`) de server day caption realtime
   cho hang tram nguoi nghe thay vi ho poll 1 giay/lan.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time as _time
import uuid

from .config import DEFAULT

SESSIONS = {}
_LOCK = threading.RLock()
_LISTENERS = {}          # sid -> list[callable(caption_dict)]
_MAX_CAP = DEFAULT.max_captions


# --------------------------------------------------------------------- PIN
def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256((salt + pin).encode("utf-8")).hexdigest()


def _new_pin_fields(pin: str):
    pin = (pin or "").strip()
    if not pin:
        return "", ""
    salt = secrets.token_hex(8)
    return salt, _hash_pin(pin, salt)


def check_pin(sid, pin="") -> bool:
    """Phong co PIN thi phai khop moi cho doc/xuat. So sanh constant-time."""
    s = get_session(sid)
    if not s:
        return False
    salt = s.get("pin_salt") or ""
    need = s.get("pin_hash") or ""
    if not need:
        return True
    got = _hash_pin((pin or "").strip(), salt)
    return hmac.compare_digest(need, got)


# --------------------------------------------------------------------- Redis
def _redis():
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis
        return redis.from_url(url, decode_responses=True)
    except Exception as e:
        print("[rooms] redis loi, fallback RAM:", e)
        return None


def _cap_key(sid):
    return f"room:{sid}:caps"


def _meta_key(sid):
    return f"room:{sid}"


# --------------------------------------------------------------------- vong doi
def create_session(topic="", pin=None, mode=None, ttl_hours=None, host=None):
    sid = uuid.uuid4().hex[:8]
    now = _time.time()
    ttl = float(ttl_hours if ttl_hours is not None else DEFAULT.session_ttl_hours)
    salt, phash = _new_pin_fields(pin or "")
    mode = (mode or DEFAULT.mode)
    if mode not in ("translate", "transcribe"):
        mode = "translate"
    data = {"sid": sid, "topic": (topic or "").strip(), "mode": mode,
            "scenario": "event", "n_speakers": 1, "ended": False,
            "pin_salt": salt, "pin_hash": phash,
            "created": now, "expires": now + ttl * 3600, "n": 0}
    r = _redis()
    if r is not None:
        try:
            r.set(_meta_key(sid), json.dumps(data, ensure_ascii=False))
            r.expire(_meta_key(sid), int(ttl * 3600))
            r.delete(_cap_key(sid))
            return sid
        except Exception:
            pass
    with _LOCK:
        SESSIONS[sid] = {**data, "captions": []}
    return sid


def get_session(sid):
    r = _redis()
    if r is not None:
        try:
            raw = r.get(_meta_key(sid))
            if raw:
                d = json.loads(raw)
                d["captions"] = get_captions(sid, 0)
                return d
            return None
        except Exception:
            pass
    with _LOCK:
        s = SESSIONS.get(sid)
        if not s:
            return None
        return {**s, "captions": list(s.get("captions", []))}


def delete_session(sid):
    r = _redis()
    if r is not None:
        try:
            r.delete(_meta_key(sid))
            r.delete(_cap_key(sid))
        except Exception:
            pass
    with _LOCK:
        SESSIONS.pop(sid, None)
        _LISTENERS.pop(sid, None)
    return True


def sweep_expired(now=None):
    """Xoa cac phong het han (RAM). Redis tu het han bang TTL."""
    now = now if now is not None else _time.time()
    dead = []
    with _LOCK:
        for sid, s in SESSIONS.items():
            if s.get("expires", 0) and s["expires"] < now:
                dead.append(sid)
        for sid in dead:
            SESSIONS.pop(sid, None)
            _LISTENERS.pop(sid, None)
    return dead


def mark_ended(sid):
    with _LOCK:
        if sid in SESSIONS:
            SESSIONS[sid]["ended"] = True
    r = _redis()
    if r is not None:
        try:
            raw = r.get(_meta_key(sid))
            if raw:
                d = json.loads(raw)
                d["ended"] = True
                r.set(_meta_key(sid), json.dumps(d, ensure_ascii=False))
        except Exception:
            pass
    return True


# --------------------------------------------------------------------- caption
def _notify(sid, cap):
    with _LOCK:
        cbs = list(_LISTENERS.get(sid, []))
    for cb in cbs:
        try:
            cb(cap)
        except Exception:
            pass


def subscribe(sid, cb):
    with _LOCK:
        _LISTENERS.setdefault(sid, []).append(cb)
    return cb


def unsubscribe(sid, cb):
    with _LOCK:
        lst = _LISTENERS.get(sid)
        if lst and cb in lst:
            lst.remove(cb)
        if lst is not None and not lst:
            _LISTENERS.pop(sid, None)


def subscribe_redis(sid, cb):
    """Nghe caption qua Redis pub/sub - DUNG KHI CHAY NHIEU WORKER/REPLICA.

    `_notify` chi day duoc cho cac listener trong CUNG process. Voi `replicas: 3`,
    nguoi nghe noi vao replica B se khong nhan duoc caption sinh ra o replica A.
    `add_caption` da `publish` vao `room:{sid}:feed`, nen o day chi can subscribe.

    Tra ve ham huy dang ky, hoac None neu khong co Redis (khi do dung _notify RAM).
    """
    r = _redis()
    if r is None:
        return None
    try:
        ps = r.pubsub(ignore_subscribe_messages=True)
        ps.subscribe(f"room:{sid}:feed")
    except Exception as e:
        print("[rooms] redis pubsub loi, fallback RAM:", e)
        return None
    stop = threading.Event()

    def _loop():
        try:
            for msg in ps.listen():
                if stop.is_set():
                    break
                if msg and msg.get("type") == "message":
                    try:
                        cb(json.loads(msg["data"]))
                    except Exception:
                        pass
        except Exception:
            pass

    threading.Thread(target=_loop, daemon=True, name=f"room-feed-{sid}").start()

    def _unsub():
        stop.set()
        try:
            ps.close()
        except Exception:
            pass
    return _unsub


def add_caption(sid, en, vi=None, speaker="Speaker 1", t_start=None, t_end=None,
                asr_ms=0.0, nmt_ms=0.0, e2e_ms=0.0, scenario=None):
    """Them 1 cau vao phong. Tra ve caption dict (co `id`) hoac None neu phong khong ton tai."""
    now = _time.time()
    r = _redis()
    if r is not None:
        try:
            raw = r.get(_meta_key(sid))
            if not raw:
                return None
            meta = json.loads(raw)
            n = int(r.incr(f"room:{sid}:n"))
            cap = {"id": n, "en": (en or "").strip(), "vi": (vi or "").strip(),
                   "speaker": speaker or "Speaker 1", "ts": now,
                   "t_start": float(t_start if t_start is not None else now),
                   "t_end": float(t_end if t_end is not None else now),
                   "asr_ms": float(asr_ms or 0), "nmt_ms": float(nmt_ms or 0),
                   "e2e_ms": float(e2e_ms or 0)}
            r.rpush(_cap_key(sid), json.dumps(cap, ensure_ascii=False))
            r.ltrim(_cap_key(sid), -_MAX_CAP, -1)
            meta["n"] = n
            if scenario:
                meta["scenario"] = scenario
            r.set(_meta_key(sid), json.dumps(meta, ensure_ascii=False))
            try:
                r.publish(f"room:{sid}:feed", json.dumps(cap, ensure_ascii=False))
            except Exception:
                pass
            _notify(sid, cap)
            return cap
        except Exception as e:
            print("[rooms] redis add_caption loi, fallback RAM:", e)

    with _LOCK:
        s = SESSIONS.get(sid)
        if not s:
            return None
        n = int(s.get("n", 0)) + 1
        s["n"] = n
        if scenario:
            s["scenario"] = scenario
        cap = {"id": n, "en": (en or "").strip(), "vi": (vi or "").strip(),
               "speaker": speaker or "Speaker 1", "ts": now,
               "t_start": float(t_start if t_start is not None else now),
               "t_end": float(t_end if t_end is not None else now),
               "asr_ms": float(asr_ms or 0), "nmt_ms": float(nmt_ms or 0),
               "e2e_ms": float(e2e_ms or 0)}
        caps = s.setdefault("captions", [])
        caps.append(cap)
        if len(caps) > _MAX_CAP:
            del caps[:len(caps) - _MAX_CAP]
    _notify(sid, cap)
    return cap


def update_caption(sid, cap_id, vi=None, nmt_ms=None, t_end=None, numbers_missing=None):
    """Cap nhat ban dich VI cho 1 cau da co (worker nen dich xong sau)."""
    with _LOCK:
        s = SESSIONS.get(sid)
        if s:
            for c in s.get("captions", []):
                if c.get("id") == cap_id:
                    if vi is not None:
                        c["vi"] = vi
                    if nmt_ms is not None:
                        c["nmt_ms"] = float(nmt_ms or 0)
                    if t_end is not None:
                        c["t_end"] = float(t_end)
                    if numbers_missing:
                        c["numbers_missing"] = numbers_missing
                    _notify(sid, dict(c))
                    return c
    r = _redis()
    if r is not None:
        try:
            items = r.lrange(_cap_key(sid), 0, -1)
            for i, raw in enumerate(items):
                c = json.loads(raw)
                if c.get("id") == cap_id:
                    if vi is not None:
                        c["vi"] = vi
                    if nmt_ms is not None:
                        c["nmt_ms"] = float(nmt_ms or 0)
                    if t_end is not None:
                        c["t_end"] = float(t_end)
                    r.lset(_cap_key(sid), i, json.dumps(c, ensure_ascii=False))
                    _notify(sid, c)
                    return c
        except Exception:
            pass
    return None


# giu tuong thich voi ban cu
def push_caption(sid, en, vi, speaker="Speaker 1"):
    return add_caption(sid, en, vi, speaker) is not None


def get_captions(sid, since=0):
    since = max(0, int(since or 0))
    r = _redis()
    if r is not None:
        try:
            if not r.exists(_meta_key(sid)):
                return []
            items = r.lrange(_cap_key(sid), since, -1)
            return [json.loads(x) for x in items]
        except Exception:
            pass
    with _LOCK:
        s = SESSIONS.get(sid)
        if not s:
            return []
        return list(s.get("captions", []))[since:]


# --------------------------------------------------------------------- export
def _fmt_ts(sec: float):
    sec = max(0, int(sec))
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_srt_time(sec: float):
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt_time(sec: float):
    return _fmt_srt_time(sec).replace(",", ".")


def export_session_txt(sid, mode="both"):
    s = get_session(sid)
    if not s:
        return None
    caps = s.get("captions", [])
    topic = s.get("topic", "")
    lines = [f"HOI THOAI EN-VI - Phong {sid}",
             f"Chu de: {topic}",
             f"Che do: {s.get('mode', 'translate')}",
             f"So cau: {len(caps)}",
             "=" * 40, ""]
    for c in caps:
        spk = c.get("speaker", "Speaker 1")
        t = _time.strftime("%H:%M:%S", _time.localtime(c.get("ts", 0)))
        en = (c.get("en") or "").strip()
        vi = (c.get("vi") or "").strip()
        if mode == "en":
            lines.append(f"[{c.get('id', '')}][{t}][{spk}] EN: {en}")
        elif mode == "vi":
            lines.append(f"[{c.get('id', '')}][{t}][{spk}] VI: {vi}")
        else:
            lines.append(f"[{c.get('id', '')}][{t}][{spk}] EN: {en}")
            lines.append(f"     VI: {vi}")
            lines.append("")
    if mode == "both":
        lines.append("=" * 40)
        lines.append("FULL TIENG VIET:")
        lines.append(" ".join((c.get("vi") or "").strip() for c in caps))
    return "\n".join(lines)


def _cue_times(caps, c, idx):
    """Thoi gian that cua 1 cue: uu tien t_start/t_end, fallback ts, fallback 3s."""
    base = caps[0].get("t_start") or caps[0].get("ts") or 0.0
    start = (c.get("t_start") or c.get("ts") or base) - base
    end = (c.get("t_end") or 0.0) - base
    if end <= start:
        nxt = caps[idx + 1] if idx + 1 < len(caps) else None
        if nxt:
            end = ((nxt.get("t_start") or nxt.get("ts") or 0.0) - base) - 0.15
        if end <= start:
            end = start + 2.5
    return max(0.0, start), max(0.0, end)


def export_session_srt(sid, lang="vi"):
    """SRT dung THOI GIAN THAT (truoc day bia 3s/cue -> lech hoan toan)."""
    s = get_session(sid)
    if not s:
        return None
    caps = [c for c in s.get("captions", [])
            if (c.get(lang) or c.get("vi") or "").strip()]
    if not caps:
        return None
    out = []
    for i, c in enumerate(caps):
        txt = (c.get(lang) or c.get("vi") or "").strip()
        start, end = _cue_times(caps, c, i)
        out += [str(i + 1), f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}",
                f"[{c.get('speaker', 'Speaker 1')}] {txt}", ""]
    return "\n".join(out)


def export_session_vtt(sid, lang="vi"):
    s = get_session(sid)
    if not s:
        return None
    caps = [c for c in s.get("captions", [])
            if (c.get(lang) or c.get("vi") or "").strip()]
    if not caps:
        return None
    out = ["WEBVTT", ""]
    for i, c in enumerate(caps):
        txt = (c.get(lang) or c.get("vi") or "").strip()
        start, end = _cue_times(caps, c, i)
        out += [str(i + 1), f"{_fmt_vtt_time(start)} --> {_fmt_vtt_time(end)}", txt, ""]
    return "\n".join(out)


def session_link(sid, host=None):
    host = (host or DEFAULT.host or "http://localhost:8000").rstrip("/")
    return f"{host}/room/{sid}"


def session_qr_png(sid, host=None):
    """Anh QR PNG (bytes) cho link phong. None neu thieu thu vien."""
    try:
        import io
        import qrcode
        img = qrcode.make(session_link(sid, host))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def session_qr(sid, host=None, out_path=None):
    """Data URL PNG (hoac link neu thieu qrcode) - dung cho API /session/create."""
    if out_path:
        png = session_qr_png(sid, host)
        if png:
            with open(out_path, "wb") as f:
                f.write(png)
            return out_path
        return session_link(sid, host)
    png = session_qr_png(sid, host)
    if png:
        return "data:image/png;base64," + base64.b64encode(png).decode()
    return session_link(sid, host)


# --------------------------------------------------------------------- bien ban
def build_minutes(sid):
    """Tom tat + action items sau cuoc hop (kieu Saydi: extract action items)."""
    from .summarizer import summarize
    s = get_session(sid)
    if not s:
        return None
    caps = s.get("captions", [])
    vi_text = " ".join((c.get("vi") or "").strip() for c in caps).strip()
    if not vi_text:
        vi_text = " ".join((c.get("en") or "").strip() for c in caps).strip()
    res = summarize(vi_text)
    res.update({"sid": sid, "topic": s.get("topic", ""), "n_captions": len(caps),
                "speakers": sorted({c.get("speaker", "Speaker 1") for c in caps}),
                "duration_sec": round((caps[-1].get("ts", 0) - caps[0].get("ts", 0)), 1)
                if len(caps) > 1 else 0})
    return res

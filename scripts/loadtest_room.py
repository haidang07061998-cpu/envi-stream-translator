"""Do suc chiu tai: BAO NHIEU NGUOI NGHE vao cung luc duoc.

Chay:
    python scripts/loadtest_room.py --n 200          # 200 nguoi nghe
    python scripts/loadtest_room.py --n 1000 --hold 30

Can server dang chay (vd run_localhost_gpu.bat).

Script lam 4 viec:
 1. Tao 1 phong che do `transcribe` (chi ASR, khong can NMT/GPU -> do nhanh)
 2. Mo N ket noi WebSocket /ws/room/{sid} CUNG LUC, dem so ket noi thanh cong
 3. Day 1 file audio qua /ws/stream de sinh caption that
 4. Dem xem bao nhieu nguoi nghe NHAN DUOC caption  -> do fan-out that su

Ket qua dung de tra loi "toi da bao nhieu nguoi" bang so do, khong phai doan.
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests                     # noqa: E402
import websockets                   # noqa: E402

CHUNK = 2048
AUDIO = "out/short_en.mp3"


async def listener(uri, idx, hold, res, start_barrier):
    """1 nguoi nghe: ket noi, nhan snapshot, dem caption trong `hold` giay."""
    try:
        async with websockets.connect(uri, open_timeout=30, max_size=2 ** 22,
                                      ping_interval=None) as ws:
            snap = await asyncio.wait_for(ws.recv(), timeout=30)
            res["connected"] += 1
            if start_barrier is not None:
                start_barrier["ready"] += 1
            got = 0
            t0 = time.time()
            while time.time() - t0 < hold:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    m = json.loads(msg)
                except Exception:
                    continue
                if m.get("kind") == "caption":
                    got += 1
            res["seen"].append(got)
    except Exception as e:
        res["failed"] += 1
        if len(res["errors"]) < 5:
            res["errors"].append(f"{type(e).__name__}: {e}")


def push_audio(host, sid, realtime=True):
    """Day audio qua /ws/stream de sinh caption (chay trong thread rieng)."""
    import websocket as wsclient
    from src.audio_utils import load_audio_16k

    url = host.replace("http://", "ws://").replace("https://", "wss://")
    url += f"/ws/stream?sid={sid}&partial=0&mode=transcribe"
    audio = load_audio_16k(AUDIO)
    ws = wsclient.create_connection(url, timeout=30)
    try:
        pace = (CHUNK / 16000) if realtime else 0.005
        for i in range(0, len(audio), CHUNK):
            pcm = (audio[i:i + CHUNK] * 32767).astype("int16")
            ws.send_binary(pcm.tobytes())
            time.sleep(pace)
        ws.send_binary(b"")                       # chot cau cuoi
        ws.settimeout(60)
        t0 = time.time()
        while time.time() - t0 < 60:
            try:
                if isinstance(ws.recv(), str):
                    break                          # da co final
            except Exception:
                break
    finally:
        try:
            ws.close()
        except Exception:
            pass


async def main_async(args):
    host = args.host.rstrip("/")
    r = requests.post(f"{host}/session/create",
                      data={"topic": "loadtest", "mode": "transcribe"}, timeout=20)
    r.raise_for_status()
    sid = r.json()["sid"]
    uri = host.replace("http://", "ws://").replace("https://", "wss://")
    uri += f"/ws/room/{sid}"
    print(f"Phong: {sid}  |  mo {args.n} ket noi toi {uri}")

    res = {"connected": 0, "failed": 0, "seen": [], "errors": []}
    ready = {"ready": 0}
    hold = args.hold + 15                          # du thoi gian cho caption

    t0 = time.time()
    tasks = [asyncio.create_task(listener(uri, i, hold, res, ready))
             for i in range(args.n)]
    # cho den khi tat ca ket noi xong (toi da 60s)
    while ready["ready"] + res["failed"] < args.n and time.time() - t0 < 60:
        await asyncio.sleep(0.3)
    t_connect = time.time() - t0
    print(f"  ket noi xong sau {t_connect:.1f}s | thanh cong {res['connected']} "
          f"| loi {res['failed']}")

    # day audio de sinh caption
    print("  day audio de sinh caption...")
    await asyncio.to_thread(push_audio, host, sid, not args.fast)

    await asyncio.gather(*tasks, return_exceptions=True)

    seen = res["seen"]
    ok_caption = sum(1 for x in seen if x > 0)
    print("\n=== KET QUA ===")
    print(f"  So ket noi yeu cau     : {args.n}")
    print(f"  Ket noi thanh cong     : {res['connected']}")
    print(f"  Ket noi that bai       : {res['failed']}")
    if seen:
        print(f"  Nhan duoc caption      : {ok_caption}/{len(seen)} "
              f"({ok_caption / len(seen) * 100:.1f}%)")
        print(f"  Caption/nguoi (tb)     : {statistics.mean(seen):.2f} "
              f"(min {min(seen)}, max {max(seen)})")
    if res["errors"]:
        print("  Loi dau tien:")
        for e in res["errors"]:
            print(f"    - {e}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200, help="so nguoi nghe")
    ap.add_argument("--host", default="http://127.0.0.1:8000")
    ap.add_argument("--hold", type=int, default=20, help="giu ket noi bao lau (giay)")
    ap.add_argument("--fast", action="store_true", help="gui audio nhanh (4x)")
    args = ap.parse_args()
    if not os.path.exists(AUDIO):
        print(f"Thieu {AUDIO}. Tao bang: python -c \"...edge_tts...\" hoac dung file khac.")
        return 1
    asyncio.run(main_async(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())

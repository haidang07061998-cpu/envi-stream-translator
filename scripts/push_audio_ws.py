"""Day 1 file audio vao server qua WS /ws/stream — test KHONG CAN MIC.

Rat huu ich khi: may khong co mic, muon test nhanh bang file co san, hoac muon do
do tre that cua ca chuoi ASR -> NMT tren server dang chay.

Vi du:
    python scripts/push_audio_ws.py --file out/e2e_en.mp3
    python scripts/push_audio_ws.py --file out/e2e_en.mp3 --sid b7fe4ee7 --mode translate
    python scripts/push_audio_ws.py --file out/e2e_en.mp3 --realtime     # gui dung 1x toc do

Script tu tao phong neu khong truyen --sid, va in ra link phong de mo tren trinh duyet.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHUNK = 2048          # mau ~ 128ms @16k, giong client that


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="file audio (wav/mp3/flac...)")
    ap.add_argument("--host", default="http://127.0.0.1:8000")
    ap.add_argument("--sid", default="", help="phong co san; bo trong thi tu tao")
    ap.add_argument("--mode", default="translate", choices=["translate", "transcribe"])
    ap.add_argument("--pin", default="")
    ap.add_argument("--fast", action="store_true",
                    help="gui nhanh ~4x (mac dinh gui dung 1x toc do nhu client that; "
                         "gui nhanh hon nua se tran buffer WebSocket)")
    ap.add_argument("--tts", action="store_true", help="yeu cau server doc tieng Viet")
    args = ap.parse_args()

    import requests
    import websocket

    from src.audio_utils import load_audio_16k

    if not args.sid:
        r = requests.post(f"{args.host}/session/create",
                          data={"topic": "test bang file", "mode": args.mode,
                                "pin": args.pin}, timeout=15)
        r.raise_for_status()
        args.sid = r.json()["sid"]
        print(f"[room] {r.json()['link']}")

    audio = load_audio_16k(args.file)
    dur = len(audio) / 16000
    print(f"[audio] {args.file} -> {dur:.1f}s @16kHz")

    ws_url = args.host.replace("http://", "ws://").replace("https://", "wss://")
    ws_url += f"/ws/stream?sid={args.sid}&partial=1&mode={args.mode}"
    if args.pin:
        ws_url += f"&pin={args.pin}"
    if args.tts:
        ws_url += "&tts=1"

    ws = websocket.create_connection(ws_url, timeout=30)
    print(f"[ws] da ket noi phong {args.sid} (mode={args.mode})")

    t_start = time.time()
    sent = 0
    finals = []

    def drain(short=0.02):
        """Doc het message dang co (khong chan). Tra ve list final moi."""
        got = []
        ws.settimeout(short)
        try:
            while True:
                msg = ws.recv()
                if not isinstance(msg, str):
                    continue
                m = json.loads(msg)
                if m.get("kind") == "partial":
                    print(f"  ~ partial EN: {m.get('en')!r}", flush=True)
                elif m.get("kind") == "final":
                    got.append(m)
                    print(f"  + FINAL EN: {m.get('en')!r}", flush=True)
                    print(f"          VI: {m.get('vi')!r}  "
                          f"(asr {m.get('asr_ms', 0):.0f}ms + "
                          f"nmt {m.get('nmt_ms', 0):.0f}ms = "
                          f"{m.get('e2e_ms', 0):.0f}ms)", flush=True)
        except Exception:
            pass
        # QUAN TRONG: tra timeout ve gia tri dai truoc khi send tiep, neu khong
        # send_binary se bi timeout khi server dang ban chay ASR.
        ws.settimeout(60)
        return got

    # Nhip gui: MAC DINH 1x toc do that (giong PWA/desktop). Client that luon gui
    # cham (~1x) va co gate im lang; gui nhanh hon nhieu se lam tran buffer WebSocket
    # phia server -> bi reset ket noi.
    pace = (CHUNK / 16000) / (4.0 if args.fast else 1.0)
    try:
        for i in range(0, len(audio), CHUNK):
            pcm = (audio[i:i + CHUNK] * 32767).astype("int16")
            ws.send_binary(pcm.tobytes())
            sent += 1
            time.sleep(pace)
            if sent % 8 == 0:
                finals += drain()
        print(f"[ws] da gui {sent} frame ({dur:.1f}s audio), bao server chot cau cuoi...")
        ws.send_binary(b"")
        deadline = time.time() + 180        # NMT tren CPU co the cham
        while time.time() < deadline:
            got = drain(1.0)
            finals += got
            if got:
                break
    finally:
        try:
            ws.close()
        except Exception:
            pass

    print(f"\n[tong] {len(finals)} cau final | thoi gian {time.time() - t_start:.1f}s")
    print(f"[mo phong] {args.host}/room/{args.sid}")
    if not finals:
        print("CANH BAO: khong co cau final nao. Kiem tra audio co tieng noi khong, "
              "hoac xem log server.")


if __name__ == "__main__":
    main()

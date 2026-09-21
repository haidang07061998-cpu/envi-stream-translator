"""Kiem tra MA QR cua phong: co dung link khong, co render duoc khong.

Chay (server dang chay):
    python scripts/check_qr.py
    python scripts/check_qr.py --host http://192.168.1.2:8000

Script kiem tra 5 thu:
 1. /health        -> dang o che do nao (offline / online, dung GPU khong)
 2. /session/create-> co tra ve link + qr khong
 3. /session/{sid}/qr.png -> PNG that, dung kich thuoc
 4. SO SANH bytes: QR server tra ve co TRUNG voi QR tu sinh tu link khong
    (=> chung minh QR ma hoa DUNG dia chi, khong phai anh rac)
 5. /room/{sid}    -> trang nguoi nghe co nut "Ma QR" va link dung
"""
import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests                     # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:8000")
    ap.add_argument("--lan", default="", help="IP LAN de tao link nguoi nghe")
    args = ap.parse_args()
    host = args.host.rstrip("/")

    ok = True
    print("=" * 66)
    print("KIEM TRA MA QR")
    print("=" * 66)

    # ---- 1. che do ----
    try:
        h = requests.get(f"{host}/health", timeout=15).json()
        nmt = h.get("nmt") or {}
        mode = "OFFLINE (CPU tai may)" if h.get("offline") else "ONLINE"
        if h.get("nmt_remote"):
            mode = f"ONLINE (GPU tu xa: {nmt.get('engine')})"
        print(f"[1] Che do      : {mode}")
        print(f"    offline={h.get('offline')} confidential={h.get('confidential')} "
              f"tts={h.get('tts')} engine={nmt.get('engine')}")
    except Exception as e:
        print(f"[1] KHONG goi duoc /health: {e}")
        return 1

    # ---- 2. tao phong ----
    lan = args.lan or host
    try:
        r = requests.post(f"{host}/session/create",
                          data={"topic": "kiem tra QR", "mode": "translate",
                                "host": lan}, timeout=20)
        r.raise_for_status()
        j = r.json()
        sid, link, qr = j["sid"], j["link"], j.get("qr", "")
        print(f"[2] Phong       : {sid}")
        print(f"    link        : {link}")
        print(f"    truong 'qr' : {'data:image/png;base64,...' if qr.startswith('data:image') else repr(qr[:60])}")
    except Exception as e:
        print(f"[2] KHONG tao duoc phong: {e}")
        return 1

    # ---- 3. qr.png ----
    png = None
    try:
        r = requests.get(f"{host}/session/{sid}/qr.png", timeout=20)
        if r.status_code == 200 and r.headers.get("content-type") == "image/png":
            png = r.content
            sig_ok = png[:8] == b"\x89PNG\r\n\x1a\n"
            print(f"[3] /qr.png     : OK - {len(png)} bytes, PNG signature "
                  f"{'dung' if sig_ok else 'SAI'}")
        else:
            ok = False
            print(f"[3] /qr.png     : LOI {r.status_code} - {r.text[:120]}")
            print("    => thieu thu vien: pip install qrcode[pil]")
    except Exception as e:
        ok = False
        print(f"[3] /qr.png     : loi {e}")

    # ---- 4. so sanh bytes voi QR tu sinh ----
    try:
        import qrcode
        buf = io.BytesIO()
        qrcode.make(link).save(buf, format="PNG")
        expect = buf.getvalue()
        if png is None:
            print("[4] So sanh     : bo qua (khong co PNG tu server)")
        elif expect == png:
            print(f"[4] So sanh     : TRUNG KHOP - QR ma hoa DUNG '{link}'")
        else:
            ok = False
            print(f"[4] So sanh     : KHAC ({len(expect)} vs {len(png)} bytes)")
            print(f"    QR server ma hoa dia chi KHAC '{link}' -> kiem tra SERVER_HOST")
    except ImportError:
        print("[4] So sanh     : bo qua (may nay khong co thu vien qrcode)")
        print("    => pip install qrcode[pil] de tu kiem chung")

    # ---- 5. trang nguoi nghe ----
    try:
        r = requests.get(f"{host}/room/{sid}", timeout=20)
        html = r.text
        has_btn = "Ma QR" in html or "btnqr" in html
        has_sid = sid in html
        print(f"[5] /room/{sid} : {r.status_code}, co nut QR: {has_btn}")
        if r.status_code != 200:
            ok = False
    except Exception as e:
        ok = False
        print(f"[5] /room/...   : loi {e}")

    # ---- ket luan ----
    print("-" * 66)
    print(f"KET LUAN: {'QR HOAT DONG DUNG' if ok else 'CO VAN DE - xem chi tiet tren'}")
    print()
    print("Cach kiem tra that (dien thoai):")
    print(f"  1. Mo {link} tren dien thoai cung WiFi")
    print("  2. Hoac bam 'Ma QR moi nguoi' tren trang /m roi quet bang dien thoai")
    print("  => Dien thoai phai thay 2 khung EN + VI va dong 'truc tiep'")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())

"""Cap nhat dia chi may GPU chi bang 1 lenh — khong phai mo file, khong phai dan dung cho.

VI SAO CAN: moi phien Kaggle/Colab la mot URL khac nhau (cloudflared quick tunnel cap
ten ngau nhien). Moi lan bat dau lam viec phai cap nhat lai URL.

CACH DUNG (nhanh nhat):
    1. Tren Kaggle: boi den dong co URL roi Ctrl+C
       (hoac bam "Copy" o goc cell - copy ca log cung duoc)
    2. Tren may ban:
           python scripts/set_gpu_url.py
       -> script tu doc CLIPBOARD, tu tim URL, luu vao gpu_url.txt, va kiem tra
          xem may do CO GPU that khong.

Cac cach khac:
    python scripts/set_gpu_url.py --url https://abc.trycloudflare.com
    python scripts/set_gpu_url.py --text "  URL CUA BAN:  https://abc.trycloudflare.com"
    python scripts/set_gpu_url.py --clear          # tat GPU, quay ve CPU tai may
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import (check_remote, extract_gpu_url, resolve_nmt_remote,  # noqa: E402
                        save_nmt_remote)


def read_clipboard() -> str:
    """Doc clipboard tren Windows khong can cai them thu vien."""
    try:
        import tkinter
        r = tkinter.Tk()
        r.withdraw()
        try:
            return r.clipboard_get()
        finally:
            r.destroy()
    except Exception:
        pass
    try:                                  # du phong: PowerShell
        import subprocess
        return subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                              capture_output=True, text=True, timeout=15).stdout
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="", help="dan thang URL")
    ap.add_argument("--text", default="", help="dan ca doan log co chua URL")
    ap.add_argument("--clear", action="store_true",
                    help="tat GPU tu xa, quay ve dich ngay tai may (CPU)")
    args = ap.parse_args()

    if args.clear:
        save_nmt_remote("")
        print("Da tat GPU tu xa. He thong se dich ngay tai may (CPU).")
        print("Khoi dong lai app/server de ap dung.")
        return 0

    raw = args.url or args.text
    src = "tham so"
    if not raw:
        raw = read_clipboard()
        src = "clipboard"
    if not raw.strip():
        print("Khong co noi dung. Hay copy dong URL tren Kaggle roi chay lai,")
        print("hoac dung: python scripts/set_gpu_url.py --url https://...")
        return 1

    url = extract_gpu_url(raw)
    if not url:
        print(f"Khong tim thay URL https:// nao trong noi dung ({src}):")
        print("   " + raw.strip()[:200])
        return 1

    print(f"Tim thay URL ({src}): {url}")
    print("Dang kiem tra may GPU...")
    info = check_remote(url, timeout=25)

    if not info.get("ok"):
        print(f"\n[!] KHONG ket noi duoc: {info.get('error')}")
        print("    Van luu URL (de lan sau thu lai)? Kiem tra:")
        print("    - Cell Kaggle con dang chay khong?")
        print("    - Da bat Internet cho notebook chua?")
        save_nmt_remote(url)
        print(f"\nDa luu {url} vao gpu_url.txt (nhung hien chua ket noi duoc).")
        return 2

    dev = info.get("device") or "?"
    eng = info.get("engine") or "?"
    asr = info.get("asr") or "?"
    save_nmt_remote(url)
    print(f"\n  engine : {eng}")
    print(f"  device : {dev}")
    print(f"  asr    : {asr}")
    if dev == "cuda":
        print("\n[OK] May do CO GPU -> da luu vao gpu_url.txt")
    else:
        print("\n[!] May do KHONG co GPU (device=" + str(dev) + ").")
        print("    Kiem tra Accelerator tren Kaggle/Colab da bat GPU chua.")
    print("\nBuoc tiep: khoi dong lai app/server de dung GPU.")
    print("  - App desktop     : run_desktop_v2.bat")
    print("  - Server localhost: run_localhost_gpu.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())

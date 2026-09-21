"""Chan doan: vi sao DIEN THOAI khong vao duoc phong qua ma QR.

Chay: python scripts/check_lan.py
     python scripts/check_lan.py --port 8000

Kiem tra 6 thu theo thu tu hay gay loi nhat:
 1. Server co dang chay khong (localhost)
 2. Server co nghe tren IP LAN khong (khong chi localhost)
 3. IP LAN nao se duoc ghi vao ma QR
 4. Windows Firewall co mo cong cho IP LAN khong   <- nguyen nhan pho bien nhat
 5. Cac adapter khac (VPN / WSL / VirtualBox) co the lam QR ghi SAI IP
 6. In huong dan xu ly
"""
import argparse
import os
import re
import socket
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests                     # noqa: E402


def lan_ip() -> str:
    """IP ma he thong dung de ra Internet (= IP ma dien thoai phai goi)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def all_ipv4() -> list:
    """Liet ke moi IP IPv4 (phat hien adapter VPN/WSL lam sai IP)."""
    ips = []
    try:
        out = subprocess.run(["ipconfig"], capture_output=True, text=True,
                             timeout=20).stdout
        for line in out.splitlines():
            m = re.search(r"IPv4[^:]*:\s*([0-9.]+)", line)
            if m:
                ips.append(m.group(1))
    except Exception:
        pass
    if not ips:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None,
                                           socket.AF_INET):
                ips.append(info[4][0])
        except Exception:
            pass
    return sorted(set(ips))


def firewall_rules(port: int) -> list:
    """Tra ve danh sach rule inbound THUC SU mo cho cong nay (ten + RemoteIP).

    Luu y cach parse: netsh in moi rule thanh 1 khoi, bat dau bang "Rule Name:"
    roi den cac thuoc tinh (Profiles / RemoteIP / LocalPort...) va cuoi cung la
    "Action:". Vi vay phai gom du ca khoi roi moi quyet dinh, KHONG duoc ket luan
    ngay khi thay Action (ban dau lam vay -> liet ke nham moi rule Action=Allow).
    """
    try:
        out = subprocess.run(["netsh", "advfirewall", "firewall", "show",
                              "rule", "name=all", "dir=in"],
                             capture_output=True, text=True, timeout=90).stdout
    except Exception:
        return []

    rules = []
    cur = None
    remote = action = ports = ""

    def flush():
        if cur and action.strip().lower() == "allow" and ports:
            if re.search(rf"(?<![\d.]){port}(?![\d.])", ports):
                rules.append({"name": cur, "remote": remote or "Any"})

    for line in out.splitlines():
        m = re.match(r"\s*Rule Name:\s+(.*)$", line)
        if m:
            flush()
            cur = m.group(1).strip()
            remote = action = ports = ""
            continue
        if cur is None:
            continue
        m = re.match(r"\s*RemoteIP:\s+(.*)$", line)
        if m:
            remote = m.group(1).strip()
            continue
        m = re.match(r"\s*Action:\s+(.*)$", line)
        if m:
            action = m.group(1).strip()
            continue
        m = re.match(r"\s*LocalPort:\s+(.*)$", line)
        if m:
            ports = m.group(1).strip()
    flush()
    return rules


def program_rules(exe: str = "python") -> list:
    """Rule inbound theo CHUONG TRINH (khong theo cong) - vd python.exe.

    Quan trong: neu co rule Allow cho python.exe o profile dang dung thi cong 8000
    van vao duoc DU khong co rule theo cong. Nguoc lai thi bi chan.
    """
    try:
        out = subprocess.run(["netsh", "advfirewall", "firewall", "show",
                              "rule", "name=all", "dir=in"],
                             capture_output=True, text=True, timeout=90).stdout
    except Exception:
        return []
    rules, cur, profiles, action, prog = [], None, "", "", ""

    def flush():
        if cur and action.strip().lower() == "allow" and exe.lower() in prog.lower():
            rules.append({"name": cur, "profiles": profiles or "?"})

    for line in out.splitlines():
        m = re.match(r"\s*Rule Name:\s+(.*)$", line)
        if m:
            flush()
            cur = m.group(1).strip()
            profiles = action = prog = ""
            continue
        if cur is None:
            continue
        m = re.match(r"\s*Profiles:\s+(.*)$", line)
        if m:
            profiles = m.group(1).strip()
            continue
        m = re.match(r"\s*Action:\s+(.*)$", line)
        if m:
            action = m.group(1).strip()
            continue
        m = re.match(r"\s*Program:\s+(.*)$", line)
        if m:
            prog = m.group(1).strip()
    flush()
    return rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="http://127.0.0.1")
    args = ap.parse_args()
    port = args.port
    ip = lan_ip()

    print("=" * 68)
    print(f"CHAN DOAN KET NOI TU DIEN THOAI  (cong {port})")
    print("=" * 68)

    problems = []

    # 1. server tren localhost
    print("\n[1] Server tren may nay")
    try:
        h = requests.get(f"{args.host}:{port}/health", timeout=8).json()
        mode = "OFFLINE" if h.get("offline") else "ONLINE"
        print(f"    OK - dang chay, che do {mode}, engine NMT {h.get('nmt', {}).get('engine')}")
    except Exception as e:
        print(f"    KHONG chay: {type(e).__name__}")
        problems.append("Server chua chay -> mo run_envi.bat truoc khi quet QR")
        print("\n=> DUNG: chua co server thi dien thoai khong the vao.")
        return 1

    # 2. server nghe tren IP LAN (khong chi localhost)
    print(f"\n[2] Server co nghe tren IP LAN {ip} khong")
    try:
        r = requests.get(f"http://{ip}:{port}/health", timeout=8)
        print(f"    OK - {ip}:{port} tra ve {r.status_code}")
    except Exception as e:
        print(f"    KHONG: {type(e).__name__}")
        problems.append(f"Server khong nghe tren {ip}:{port} -> kiem tra da chay "
                        f"voi --host 0.0.0.0 chua")

    # 3. IP se ghi vao QR
    print(f"\n[3] IP se duoc ghi vao ma QR")
    print(f"    http://{ip}:{port}/room/<sid>")
    ips = all_ipv4()
    print(f"    Cac IP khac tren may: {', '.join(x for x in ips if x != ip) or '(khong co)'}")
    if len([x for x in ips if not x.startswith(("127.", "169.254."))]) > 1:
        print("    [!] May co NHIEU IP -> neu QR ghi sai IP, dien thoai se khong vao duoc")
        print("        (thuong do VPN / WSL / VirtualBox). Tat VPN roi chay lai.")

    # 4. firewall
    print(f"\n[4] Windows Firewall cho cong {port}   <-- nguyen nhan pho bien nhat")
    rules = firewall_rules(port)
    subnet = ip.rsplit(".", 1)[0]

    def covers(r) -> bool:
        remote = (r.get("remote") or "Any").strip()
        return remote.lower().startswith("any") or subnet in remote

    if not rules:
        print(f"    KHONG co rule nao mo cong {port} inbound")
        problems.append(f"Chua mo cong {port} tren firewall -> dien thoai bi chan")
    else:
        any_ok = False
        for r in rules:
            ok_scope = covers(r)
            any_ok = any_ok or ok_scope
            print(f"    rule cong : {r['name']}  |  RemoteIP: {r.get('remote') or 'Any'}"
                  f"  |  {'PHU HOP' if ok_scope else 'khong phu hop (khong sao neu co rule khac)'}")
        if any_ok:
            print("    => OK: da co it nhat 1 rule mo cong cho IP cua ban")
        else:
            problems.append(f"Tat ca rule cong {port} deu KHONG gom IP {ip} "
                            f"-> dien thoai bi chan. Chay scripts\\open_firewall.ps1")

    progs = program_rules("python")
    if progs:
        names = ", ".join(f"{p['name']}({p['profiles']})" for p in progs[:4])
        print(f"    rule chuong trinh python: {names}")
        print("    (rule theo chuong trinh cung cho phep vao, neu dung profile)")

    # 5. ket luan
    print("\n" + "=" * 68)
    if problems:
        print("VAN DE TIM THAY:")
        for i, p in enumerate(problems, 1):
            print(f"  {i}. {p}")
        print("\nCACH SUA NHANH NHAT:")
        print("  - Mo PowerShell bang quyen Administrator, chay:")
        print(f'    netsh advfirewall firewall add rule name="EN-VI Translator {port}" '
              f"dir=in action=allow protocol=TCP localport={port} profile=any")
        print("  - Hoac chay: powershell -ExecutionPolicy Bypass -File scripts\\open_firewall.ps1")
    else:
        print("KHONG THAY VAN DE TU PHIA MAY CHU.")
        print("Neu dien thoai van khong vao duoc, kiem tra:")
        print(f"  1. Dien thoai co cung WiFi khong? (khong dung 4G/5G)")
        print(f"  2. Thu mo truc tiep tren dien thoai: http://{ip}:{port}/health")
        print(f"     - Neu hien JSON  -> server OK, chi la van de ma QR")
        print(f"     - Neu 'khong ket noi duoc' -> firewall hoac router chan")
        print("  3. Router co bat 'AP isolation' / 'Client isolation' khong?")
        print("     (thuong co o WiFi khach / guest network) -> tat hoac dung WiFi chinh")
        print("  4. Thu tat VPN tren may tinh")
    print("=" * 68)
    return 0 if not problems else 2


if __name__ == "__main__":
    sys.exit(main())

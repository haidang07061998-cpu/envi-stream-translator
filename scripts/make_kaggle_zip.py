"""Dong goi code thanh zip de upload len Kaggle Dataset.

Chay: python scripts/make_kaggle_zip.py

VI SAO KHONG DUNG Compress-Archive CUA POWERSHELL:
    PowerShell ghi ten file trong zip bang dau '\\' (vd "envi-stream-translator\\app\\server.py"),
    nhung chuan ZIP yeu cau dau '/'. Kaggle (va nhieu cong cu khac) TU CHOI:
        "... contains a forbidden character in name ('\\')"
    Python zipfile ghi dung '/' -> Kaggle nhan.

Script nay cung loai bo rac: models/ (1.7GB), out/, .git/, __pycache__, file log, sid.txt...
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "dist")
ZIP_NAME = "envi-stream-translator-kaggle.zip"
TOP = "envi-stream-translator"          # thu muc goc trong zip

SKIP_DIRS = {"models", "out", ".git", "__pycache__", ".playwright-mcp", ".venv",
             "venv", "dist", "node_modules", ".idea", ".vscode", ".pytest_cache"}
SKIP_FILES = {"sid.txt", "t_check.js", "mobile_script_check.js", "test_out.txt"}
SKIP_EXT = {".log", ".zip", ".pyc", ".tmp", ".onnx", ".bin", ".dsp"}


def should_skip_dir(name):
    return name in SKIP_DIRS


def should_skip_file(name):
    if name in SKIP_FILES:
        return True
    return os.path.splitext(name)[1].lower() in SKIP_EXT


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    zip_path = os.path.join(OUT_DIR, ZIP_NAME)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for cur, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if not should_skip_dir(d)]
            rel_dir = os.path.relpath(cur, ROOT)
            for f in files:
                if should_skip_file(f):
                    continue
                full = os.path.join(cur, f)
                if os.path.islink(full):
                    continue
                # arcname LUON dung '/' (chuan ZIP) - day la diem quan trong nhat
                if rel_dir == ".":
                    arc = f"{TOP}/{f}"
                else:
                    arc = f"{TOP}/" + rel_dir.replace(os.sep, "/") + f"/{f}"
                z.write(full, arc)
                n += 1

    # ---- kiem tra lai: khong duoc co dau '\\' trong ten entry ----
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        bad = [x for x in names if "\\" in x]
        size_kb = os.path.getsize(zip_path) / 1024
        has_server = any(x.endswith("app/server.py") for x in names)
        has_script = any(x.endswith("scripts/colab_kaggle_server.py") for x in names)
        has_models = any("/models/" in x for x in names)

    print(f"Da tao : {zip_path}")
    print(f"So file: {len(names)}  |  Kich thuoc: {size_kb:.0f} KB")
    print(f"Entry co dau '\\' (LOI Kaggle): {len(bad)}")
    print(f"Co app/server.py            : {has_server}")
    print(f"Co scripts/colab_kaggle_server.py: {has_script}")
    print(f"Co models/ (khong nen co)   : {has_models}")
    if bad:
        print("\n[!!] VAN CON DAU '\\' - Kaggle se tu choi. Vi du:")
        for x in bad[:3]:
            print("   ", x)
        sys.exit(1)
    print("\nOK - san sang upload len Kaggle (Datasets > New Dataset).")


if __name__ == "__main__":
    main()

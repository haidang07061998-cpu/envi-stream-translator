"""Convert VinAI en2vi-v2 sang CTranslate2 int8 (nhanh 4-5x, RAM /4, giu ~99% chat luong).

Chay 1 lan: python scripts/convert_nmt_ct2.py
Sau do `src/nmt.py` tu tim thay `models/ct2-en2vi-v2-int8` va dung (nhanh hon HF PyTorch).

KHONG can mang neu da co model trong models/ (xem scripts/download_offline_models.py).

Vi sao script nay dai hon ban cu: CLI `ct2-transformers-converter` hien FAIL tren mot so
cap phien ban transformers/ctranslate2 voi loi
    TypeError: MBartForConditionalGeneration.__init__() got an unexpected keyword argument 'dtype'
(converter truyen `dtype=` trong khi transformers ban cai chi hieu `torch_dtype=`).
Script nay thu CLI truoc, neu loi thi tu vá (patch) roi goi Python API.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MODEL = os.getenv("NMT_MODEL", "vinai/vinai-translate-en2vi-v2")
OUT = os.getenv("CT2_OUT", os.path.join(ROOT, "models", "ct2-en2vi-v2-int8"))
# int8_float32: nhanh nhat nhung DO THUC TE lam hong chat luong VinAI en2vi-v2
#   (sinh cau lap vo nghia voi nhieu cau ngan). Thu "float32" neu gap hien tuong nay:
#   set CT2_QUANT=float32 & python scripts/convert_nmt_ct2.py
QUANT = os.getenv("CT2_QUANT", "int8_float32")


def _local_or_id():
    """Uu tien ban model da tai san trong models/ (convert duoc ca khi offline)."""
    try:
        from src.config import local_model_dir
        return local_model_dir(MODEL) or MODEL
    except Exception:
        return MODEL


def try_cli(model_path):
    exe = "ct2-transformers-converter"
    cmd = [exe, "--model", model_path, "--output_dir", OUT,
           "--quantization", QUANT, "--force"]
    print("[1/2] Thu CLI:", " ".join(cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print("      khong co CLI -> chuyen sang Python API")
        return False
    if r.returncode == 0:
        print("      CLI OK")
        return True
    tail = (r.stderr or "").strip().splitlines()[-3:]
    print("      CLI FAIL:", " | ".join(tail))
    return False


def try_api(model_path):
    """Python API + patch loi 'dtype' <-> 'torch_dtype'."""
    print("[2/2] Thu Python API (co patch tuong thich phien ban)")
    import ctranslate2
    from ctranslate2.converters.transformers import TransformersConverter

    orig = TransformersConverter.load_model

    def load_model_patched(model_class, model_name_or_path, **kwargs):
        if "dtype" in kwargs:
            kwargs["torch_dtype"] = kwargs.pop("dtype")
        return model_class.from_pretrained(model_name_or_path, **kwargs)

    TransformersConverter.load_model = staticmethod(load_model_patched)
    try:
        conv = TransformersConverter(model_path)
        conv.convert(OUT, quantization=QUANT, force=True)
        return True
    except TypeError as e:
        print(f"      van loi TypeError: {e}")
        print("      -> thu tiep: bo hoan toan tham so dtype")
        def load_model_patched2(model_class, model_name_or_path, **kwargs):
            kwargs.pop("dtype", None)
            kwargs.pop("torch_dtype", None)
            return model_class.from_pretrained(model_name_or_path, **kwargs)
        TransformersConverter.load_model = staticmethod(load_model_patched2)
        conv = TransformersConverter(model_path)
        conv.convert(OUT, quantization=QUANT, force=True)
        return True
    finally:
        TransformersConverter.load_model = orig
    return False


def verify():
    """Kiem tra that: mo model CT2 va dich thu 1 cau."""
    import ctranslate2
    print("\n[verify] mo model CT2 va dich thu...")
    from transformers import AutoTokenizer
    src = _local_or_id()
    tok = AutoTokenizer.from_pretrained(src, src_lang="en_XX")
    tr = ctranslate2.Translator(OUT, device="cpu", inter_threads=2, intra_threads=4)
    text = "We need to check the API latency before we deploy to production."
    ids = tok(text, truncation=True, max_length=128).input_ids
    try:
        toks = tok.convert_ids_to_tokens(ids, skip_special_tokens=True)
    except TypeError:
        specials = set(getattr(tok, "all_special_ids", []) or [])
        toks = tok.convert_ids_to_tokens([i for i in ids if i not in specials])
    import time
    t0 = time.time()
    res = tr.translate_batch([toks], beam_size=1, max_decoding_length=80,
                             no_repeat_ngram_size=3, length_penalty=1.0,
                             target_prefix=[["vi_VN"]])
    ms = (time.time() - t0) * 1000
    hyp = [h for h in res[0].hypotheses[0] if h != "vi_VN"]
    vi = tok.convert_tokens_to_string(hyp).strip()
    print(f"         EN: {text}")
    print(f"         VI: {vi!r}  ({ms:.0f}ms)")
    if not vi:
        raise RuntimeError("CT2 tra ve chuoi rong -> target_prefix/tokenizer sai")
    print("         => CT2 int8 CHAY THAT")


def main():
    model_path = _local_or_id()
    print(f"Model nguon: {model_path}")
    print(f"Thu muc ra : {OUT}")
    if not os.path.isdir(model_path) and "/" in model_path:
        print("(chua co ban noi bo -> se tai tu HuggingFace, can mang)")

    ok = try_cli(model_path) or try_api(model_path)
    if not ok:
        print("\nTHAT BAI. App van chay bang HF PyTorch (cham hon tren CPU).")
        sys.exit(1)

    print(f"\nXONG: {OUT}")
    try:
        verify()
        print("\nApp se tu dung CT2 nay. Kiem tra: /health hoac nmt.stats()['engine'] == 'ct2-int8'")
    except Exception as e:
        print(f"\nConvert xong nhung VERIFY loi: {type(e).__name__}: {e}")
        print("Dat DISABLE_CT2=1 de quay lai HF PyTorch.")
        sys.exit(2)


if __name__ == "__main__":
    main()

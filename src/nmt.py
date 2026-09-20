"""NMT En -> Vi. VinAI `vinai-translate-en2vi-v2` (SOTA chuyen En-Vi, 448M).

Duong chay:
- CTranslate2 int8 (neu co `models/ct2-en2vi-v2-int8`): nhanh 4-5x, RAM /4
- HF PyTorch (fallback): beam thap khi CPU, beam cao khi GPU

Sua loi ban cu:
1. CT2 `target_prefix` truyen **id so** trong khi CTranslate2 yeu cau **token string**
   ("vi_VN") -> luon nem loi, bi `except: pass` nuot -> thuc te CHUA BAO GIO chay CT2.
   Gio truyen token string, kiem tra ket qua rong, va GHI LAI loi dau tien vao
   `self.ct2_error` thay vi im lang.
2. Cache tra `ms = 0.0` -> `mean_nmt` trong bao cao bi thap gia tao. Gio do thoi gian that.
3. `_cache_order` khong quan ly key "legacy" -> cache phinh qua gioi han. Gio LRU dung nghia.
4. `postprocess` hook de ep thuat ngu (Context Engine) ma khong phai monkeypatch class.
"""
import time
import os
import re
from typing import List


def split_sentences_en(text: str):
    """Tach cau EN dai thanh manh ngan de NMT khong truncate + giu nghia."""
    t = (text or "").strip()
    if not t:
        return []
    parts = re.split(r'(?<=[.!?])\s+', t)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        words = p.split()
        if len(words) <= 40:
            out.append(p)
        else:
            for i in range(0, len(words), 30):
                out.append(" ".join(words[i:i + 30]))
    return out or [t]


def looks_degenerate(text: str) -> bool:
    """Phat hien decoder bi LAP VO NGHIA.

    Do thuc te: CT2 int8_float32 cua VinAI en2vi-v2 sinh ra
    'Chung Chung Chung chung Chung Chung We Chung Chung Can ...' — cau dung bi lap
    hang chuc lan. Neu khong chan, ban dich se rac ma khong bao loi.
    """
    words = [w for w in (text or "").split() if w]
    if len(words) < 6:
        return False
    low = [w.lower().strip(".,!?…:;\"'()") for w in words]
    if len(set(low)) / len(low) < 0.45:          # qua it tu khac nhau
        return True
    from collections import Counter
    bigrams = Counter(zip(low, low[1:]))
    if bigrams and bigrams.most_common(1)[0][1] >= 3:   # 2-gram lap >= 3 lan
        return True
    run = 1
    for a, b in zip(low, low[1:]):
        run = run + 1 if a == b else 1
        if run >= 3:                              # 1 tu lap lien tiep >= 3 lan
            return True
    return False


CT2_SELFTEST_SENTENCE = "We need to check the API latency before we deploy."


def ct2_enabled() -> bool:
    """CT2 co duoc phep dung khong. MAC DINH TAT (xem ghi chu trong NMTTranslator).

    Do thuc te: CT2 int8_float32 lam hong chat luong VinAI en2vi-v2 voi nhieu cau ngan.
    """
    return (os.getenv("ENABLE_CT2", "0") == "1"
            and os.getenv("DISABLE_CT2", "0") != "1")


class NMTTranslator:
    """NMT En->Vi. Live: beam=1 (~80-170ms CPU voi CT2 int8). Final: beam cao hon."""

    def __init__(self, model_id="vinai/vinai-translate-en2vi-v2",
                 src="en_XX", tgt="vi_VN", device="auto", max_len=96,
                 num_beams=1, ct2_path=None, accurate_beams=None,
                 cache_size=500, postprocess=None):
        import torch
        from .config import local_model_dir

        self.model_id = model_id
        # Uu tien ban model da tai san trong models/ -> chay offline that su
        # (khong can cache HuggingFace, khong can mang).
        local = local_model_dir(model_id)
        self.load_path = local or model_id
        model_id = self.load_path
        self.src, self.tgt = src, tgt
        self.max_len = min(int(max_len), 96)
        self.num_beams = num_beams
        self.postprocess = postprocess      # callable(str) -> str (ep thuat ngu)
        self.ct2_error = None
        self._ct2_failed_once = False

        if accurate_beams is None and os.getenv("ACCURATE_BEAMS"):
            try:
                accurate_beams = int(os.getenv("ACCURATE_BEAMS"))
            except Exception:
                accurate_beams = None
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.accurate_beams = accurate_beams if accurate_beams else (4 if device == "cuda" else 2)

        try:
            n = os.cpu_count() or 4
            torch.set_num_threads(max(1, min(n, 8)))
            torch.set_num_interop_threads(1)
        except Exception:
            pass

        low = model_id.lower()
        self.is_vinai = "vinai-translate" in low
        self.is_nllb = "nllb" in low

        # ---------------- thu CTranslate2 (PHAI BAT TAY bang ENABLE_CT2=1) ----------------
        # MAC DINH TAT. Ly do do thuc te: CT2 cua VinAI en2vi-v2 sinh ra cau lap vo nghia
        # voi nhieu cau ngan (vd 'We need to check the budget.' -> 'Chung Chung Chung
        # chung Chung Chung We Chung...'), trong khi cung cau do qua HF PyTorch lai dung.
        # DA THU CA int8_float32 VA float32 -> ca hai deu hong => loi o buoc convert mBART
        # sang CTranslate2, khong phai o luong tu hoa. Nhanh ma rac thi te hon cham ma dung.
        #   Bat: set ENABLE_CT2=1   (van co self-test + guard chong lap)
        #   Tat han: set DISABLE_CT2=1
        self.ct2 = None
        self.ct2_tok = None
        want_ct2 = ct2_enabled()
        if not want_ct2:
            self.ct2_error = ("CT2 dang TAT (mac dinh). Bat bang ENABLE_CT2=1 neu ban "
                              "da kiem tra chat luong.")
        else:
            candidates = [ct2_path, os.getenv("CT2_EN2VI"), "models/ct2-en2vi-v2-int8",
                          "ct2-en2vi-v2-int8"]
            for c in candidates:
                if c and os.path.isdir(c):
                    try:
                        import ctranslate2
                        ncore = os.cpu_count() or 4
                        self.ct2 = ctranslate2.Translator(
                            c, device="cuda" if device == "cuda" else "cpu",
                            inter_threads=2, intra_threads=max(1, min(4, ncore)))
                        from transformers import AutoTokenizer as _AT
                        self.ct2_tok = (_AT.from_pretrained(model_id, src_lang=self.src)
                                        if self.is_vinai else _AT.from_pretrained(model_id))
                        self.ct2_dir = c
                        self.ct2_error = None
                        break
                    except Exception as e:
                        self.ct2 = None
                        self.ct2_tok = None
                        self.ct2_error = f"{type(e).__name__}: {e}"

        # --- SELF-TEST CT2: luong tu hoa co the lam decoder lap vo nghia ---
        # Phai chay TRUOC khi chon nhanh HF, neu khong se khong con model nao de dung.
        if self.ct2 is not None and self.is_vinai:
            self._ct2_selftest()

        # ---------------- HF PyTorch ----------------
        self.pipe = None
        self.model = None
        if self.ct2 is None:
            from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
            if self.is_vinai:
                self.tok = AutoTokenizer.from_pretrained(model_id, src_lang=self.src)
                self.model = AutoModelForSeq2SeqLM.from_pretrained(model_id).to(device).eval()
                try:
                    if device == "cuda":
                        self.model = self.model.half()
                except Exception:
                    pass
                self.vi_id = self.tok.lang_code_to_id[self.tgt]
            else:
                self.tok = AutoTokenizer.from_pretrained(model_id)
                from transformers import pipeline as hf_pipe
                d = 0 if device == "cuda" else -1
                self.pipe = hf_pipe("translation", model=model_id,
                                    tokenizer=self.tok, device=d, max_length=self.max_len)
        else:
            self.tok = self.ct2_tok
            self.vi_id = None
            if self.is_vinai:
                try:
                    self.vi_id = self.tok.lang_code_to_id[self.tgt]
                except Exception:
                    self.vi_id = None

        self._cache = {}
        self._cache_order = []
        self.cache_size = int(cache_size)
        self.cache_hits = 0
        self.cache_misses = 0
        self.ct2_degenerate = 0

    # ------------------------------------------------------------------
    def _ct2_selftest(self):
        """Dich thu 1 cau co dinh. Neu lap vo nghia -> TAT CT2 ngay.

        Do thuc te: CT2 int8_float32 lam hong chat luong VinAI en2vi-v2 tren may nay
        (sinh 'Chung Chung Chung chung...'). Tha cham ma dung con hon nhanh ma rac.
        """
        try:
            out = self._ct2_vinai(CT2_SELFTEST_SENTENCE, 1)
        except Exception as e:
            self.ct2_error = f"self-test loi: {type(e).__name__}: {e}"
            print(f"[NMT] CT2 self-test loi ({self.ct2_error}) -> dung HF PyTorch.")
            self.ct2 = None
            self.ct2_tok = None
            return
        if not out or looks_degenerate(out):
            self.ct2_error = f"self-test: ket qua lap vo nghia ({out[:70]!r})"
            print(f"[NMT] {self.ct2_error}")
            print("[NMT] => TAT CT2, dung HF PyTorch (cham hon nhung DUNG). "
                  "Co the thu lai voi quantization float32: "
                  "python scripts/convert_nmt_ct2.py")
            self.ct2 = None
            self.ct2_tok = None
            return
        print(f"[NMT] CT2 self-test OK: {out!r}")

    # ------------------------------------------------------------------
    @property
    def engine(self) -> str:
        if self.ct2 is not None:
            return "ct2-int8"
        return "hf-" + self.device

    def set_glossary(self, terms: dict):
        """Ep thuat ngu EN->VI ngay trong NMT (thay cho viec boc class ben ngoai)."""
        terms = dict(terms or {})
        if not terms:
            self.postprocess = None
            return
        pats = [(re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE), v)
                for k, v in sorted(terms.items(), key=lambda x: -len(x[0])) if k and v]

        def _apply(s: str) -> str:
            out = s
            for p, v in pats:
                if p.search(out):
                    out = p.sub(v, out)
            return out

        self.postprocess = _apply

    def _post(self, s: str) -> str:
        if not s:
            return s
        try:
            return self.postprocess(s) if self.postprocess else s
        except Exception:
            return s

    # ------------------------------------------------------------------
    def _hf_vinai(self, t: str, beams: int):
        import torch
        ids = self.tok(t, return_tensors="pt", truncation=True,
                       max_length=128).input_ids.to(self.device)
        # early_stopping chi co y nghia khi beam > 1 (neu khong transformers canh bao)
        extra = {"early_stopping": True} if beams > 1 else {}
        with torch.no_grad():
            try:
                out = self.model.generate(
                    ids, decoder_start_token_id=self.vi_id,
                    num_beams=beams, max_new_tokens=80,
                    no_repeat_ngram_size=3, length_penalty=1.0, **extra)
            except TypeError:
                out = self.model.generate(
                    ids, decoder_start_token_id=self.vi_id,
                    num_beams=beams, max_length=self.max_len, **extra)
        return self.tok.batch_decode(out, skip_special_tokens=True)[0].strip()

    def _ct2_vinai(self, t: str, beams: int):
        """CTranslate2: token hoa bang tokenizer HF -> token STRING cho CT2."""
        ids = self.ct2_tok(t, truncation=True, max_length=128).input_ids
        try:
            toks = self.ct2_tok.convert_ids_to_tokens(ids, skip_special_tokens=True)
        except TypeError:
            specials = set(getattr(self.ct2_tok, "all_special_ids", []) or [])
            toks = self.ct2_tok.convert_ids_to_tokens([i for i in ids if i not in specials])
        if not toks:
            raise ValueError("CT2: khong token hoa duoc input")
        # mBART/VinAI: decoder phai bat dau bang token ngon ngu dich (STRING, khong phai id)
        res = self.ct2.translate_batch(
            [toks], beam_size=beams, max_decoding_length=80,
            no_repeat_ngram_size=3, length_penalty=1.0,
            target_prefix=[[self.tgt]])
        hyp = list(res[0].hypotheses[0])
        hyp = [h for h in hyp if h != self.tgt]
        out = self.ct2_tok.convert_tokens_to_string(hyp).strip()
        if not out:
            raise ValueError("CT2: ket qua rong")
        return out

    def _translate_one(self, t: str, beams: int):
        t = (t or "").strip()
        if not t:
            return ""
        if len(t.split()) > 40 or len(t) > 300:
            parts = split_sentences_en(t)
            outs = [self._translate_one(p, beams) for p in parts if p.strip()]
            return " ".join(o for o in outs if o).strip()

        if self.ct2 is not None and self.is_vinai:
            try:
                out = self._ct2_vinai(t, beams)
                if out and not looks_degenerate(out):
                    return self._post(out)
                # CT2 sinh ket qua lap -> KHONG tra rac cho nguoi dung
                self.ct2_degenerate += 1
                print(f"[NMT] CT2 tra ket qua lap (lan {self.ct2_degenerate}) "
                      f"-> dung HF cho cau nay")
                if self.ct2_degenerate >= 3:
                    self.ct2_error = "tat sau 3 lan sinh ket qua lap"
                    print("[NMT] => TAT CT2 (chat luong khong dam bao), "
                          "dung HF PyTorch tu day.")
                    self.ct2 = None
                    self.ct2_tok = None
            except Exception as e:
                if not self._ct2_failed_once:
                    self._ct2_failed_once = True
                    self.ct2_error = f"{type(e).__name__}: {e}"
                    print(f"[NMT] CT2 loi lan dau ({self.ct2_error}) -> dung HF PyTorch. "
                          f"Kiem tra: python scripts/convert_nmt_ct2.py")
        if self.is_vinai:
            return self._post(self._hf_vinai(t, beams))
        if self.is_nllb:
            outs = self.pipe([t], src_lang=self.src, tgt_lang=self.tgt)
            return self._post(outs[0]["translation_text"].strip())
        outs = self.pipe([t])
        return self._post(outs[0]["translation_text"].strip())

    # ------------------------------------------------------------------
    def translate(self, texts: str | List[str], accurate: bool = False):
        """Dich EN->VI.

        accurate=False (live/partial): beam=1, nhanh nhat
        accurate=True  (final)       : beam=accurate_beams
        Tra ve (vi, ms) hoac (list_vi, ms). ms la thoi gian THAT (ke ca khi cache hit).
        """
        single = isinstance(texts, str)
        if single:
            texts = [texts]
        texts = [t.strip() for t in texts]
        if single and not texts[0]:
            return ("", 0.0)
        if not single and all(not t for t in texts):
            return (["" for _ in texts], 0.0)

        beams = self.accurate_beams if accurate else self.num_beams
        t0 = time.time()

        if single:
            ckey = (texts[0], beams)
            if ckey in self._cache:
                self.cache_hits += 1
                self._cache_order.remove(ckey)
                self._cache_order.append(ckey)
                return (self._cache[ckey], (time.time() - t0) * 1000)

        hyp = [self._translate_one(t, beams) for t in texts]
        ms = (time.time() - t0) * 1000

        for src_t, h in zip(texts, hyp):
            k = (src_t, beams)
            if k in self._cache:
                self.cache_misses += 1
                self._cache_order.remove(k)
            self._cache[k] = h
            self._cache_order.append(k)
        while len(self._cache_order) > self.cache_size:
            old = self._cache_order.pop(0)
            self._cache.pop(old, None)
        return (hyp[0], ms) if single else (hyp, ms)

    def stats(self) -> dict:
        return {"engine": self.engine, "device": self.device,
                "live_beams": self.num_beams, "final_beams": self.accurate_beams,
                "cache": len(self._cache), "cache_hits": self.cache_hits,
                "ct2_error": self.ct2_error}


def finetune_nmt_lora(base_id="facebook/nllb-200-distilled-600M",
                      train_file="data/train.ted.jsonl",
                      out_dir="models/envi-ted-v1",
                      epochs=5, lr=2e-4):
    """Stub fine-tune LoRA (chay tren Kaggle GPU). Moi dong: {"en":..,"vi":..}."""
    from datasets import load_dataset
    from transformers import (AutoTokenizer, AutoModelForSeq2SeqLM,
                              Seq2SeqTrainingArguments, Seq2SeqTrainer,
                              DataCollatorForSeq2Seq)
    from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
    import torch
    tok = AutoTokenizer.from_pretrained(base_id)
    model = AutoModelForSeq2SeqLM.from_pretrained(base_id, load_in_8bit=True, device_map="auto")
    model = prepare_model_for_kbit_training(model)
    cfg = LoraConfig(task_type=TaskType.SEQ_2_SEQ_LM, r=16, lora_alpha=32,
                     lora_dropout=0.05, target_modules=["q_proj", "v_proj"])
    model = get_peft_model(model, cfg)
    ds = load_dataset("json", data_files=train_file)["train"]

    def prep(b):
        m = tok(b["en"], truncation=True, max_length=128)
        lab = tok(text_target=b["vi"], truncation=True, max_length=128)
        m["labels"] = lab["input_ids"]
        return m

    ds = ds.map(prep, batched=True, remove_columns=ds.column_names)
    args = Seq2SeqTrainingArguments(out_dir, per_device_train_batch_size=8,
                                    num_train_epochs=epochs, learning_rate=lr,
                                    fp16=torch.cuda.is_available(),
                                    logging_steps=50, save_steps=500,
                                    predict_with_generate=True)
    tr = Seq2SeqTrainer(model=model, args=args, train_dataset=ds,
                        data_collator=DataCollatorForSeq2Seq(tok, model))
    tr.train()
    tr.save_model(out_dir)
    return out_dir

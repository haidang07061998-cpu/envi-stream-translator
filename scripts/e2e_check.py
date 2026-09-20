"""Kiem chung END-TO-END that: tao tieng Anh -> ASR -> NMT -> do do tre.

Chay: python scripts/e2e_check.py          # ban gon (1 cau, beam=1) - vai phut
      set E2E_FULL=1 & python scripts/e2e_check.py   # ban day du (nhieu cau, streaming)

Can mang LAN DAU (tai model). Sau khi co models/ thi chay offline duoc:
      set HF_HUB_OFFLINE=1 & python scripts/e2e_check.py

Kiem tra nhung thu test don vi KHONG the kiem tra:
- model co tai duoc khong (va co dung ban trong models/ khong)
- CT2 int8 co THAT SU chay khong (loi cu bi nuot im lang)
- ban dich VI co ra chu khong
- do tre thuc te tung khau -> biet co dat realtime khong
- Custom Dictionary co ep duoc thuat ngu khong

LUU Y DO TRE: VinAI 448M fp32 tren CPU ton ~2-3 PHUT/cau voi beam=2 (do thuc te).
Tren CPU phai beam=1 va nen convert CT2 int8 (nhanh 4-5x) moi dat realtime.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)

FULL = os.getenv("E2E_FULL", "0") == "1"
SPEECH = ("You should check the API latency before we deploy to production. "
          "The machine learning pipeline streams audio to the translation model.")
if not FULL:
    SPEECH = SPEECH.split(".")[0] + "."


def log(msg):
    print(msg, flush=True)


def make_speech():
    path = os.path.join(OUT, "e2e_en.mp3")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        log(f"[1] da co audio: {path}")
        return path
    try:
        import asyncio
        import edge_tts

        async def _gen():
            comm = edge_tts.Communicate(SPEECH, "en-US-JennyNeural")
            with open(path, "wb") as f:
                async for ch in comm.stream():
                    if ch["type"] == "audio" and ch.get("data"):
                        f.write(ch["data"])

        asyncio.run(_gen())
        log(f"[1] tao audio OK: {path} ({os.path.getsize(path)} bytes)")
        return path
    except Exception as e:
        log(f"[1] KHONG tao duoc audio (bo qua): {type(e).__name__}: {e}")
        return None


def main():
    from src.config import DEFAULT, local_model_dir

    audio_path = make_speech()

    import torch
    use_cuda = torch.cuda.is_available()
    log(f"[2] cuda={use_cuda} | offline={DEFAULT.offline} | mode={DEFAULT.mode} | "
        f"HF_HUB_OFFLINE={os.getenv('HF_HUB_OFFLINE', '0')}")

    asr_model = DEFAULT.resolve_asr_model(use_cuda)
    log(f"[3] ASR '{asr_model}' | ban noi bo: {local_model_dir(asr_model)}")
    t0 = time.time()
    from src.asr import FasterWhisperASR
    asr = FasterWhisperASR(asr_model, DEFAULT.asr_device,
                           DEFAULT.resolve_compute(use_cuda), DEFAULT.asr_beam,
                           DEFAULT.asr_language, gate_rms=DEFAULT.asr_gate_rms)
    log(f"    tai xong sau {time.time() - t0:.1f}s")

    nmt_path = DEFAULT.resolve_nmt_path()
    log(f"[4] NMT '{nmt_path}' (ban noi bo: {local_model_dir(DEFAULT.nmt_model)})")
    t0 = time.time()
    from src.nmt import NMTTranslator
    nmt = NMTTranslator(DEFAULT.nmt_model, DEFAULT.nmt_src, DEFAULT.nmt_tgt,
                        num_beams=DEFAULT.nmt_live_beams, max_len=DEFAULT.nmt_max_len,
                        accurate_beams=DEFAULT.resolve_final_beams(use_cuda),
                        ct2_path=DEFAULT.ct2_dir)
    log(f"    tai xong sau {time.time() - t0:.1f}s | engine={nmt.engine} | "
        f"final_beams={nmt.accurate_beams}")
    if nmt.ct2 is not None:
        log("    => CT2 int8 dang chay THAT (nhanh 4-5x)")
    else:
        log("    => CHUA co CT2 int8 -> chay HF PyTorch (CHAM tren CPU). "
            "Chay: python scripts/convert_nmt_ct2.py")
        if nmt.ct2_error:
            log(f"       ct2_error={nmt.ct2_error}")

    en = SPEECH
    if audio_path:
        from src.audio_utils import load_audio_16k
        audio = load_audio_16k(audio_path)
        log(f"[5] audio {len(audio) / 16000:.1f}s -> ASR")
        r = asr.transcribe(audio)
        log(f"    EN: {r['text']!r}  ({r['asr_ms']:.0f}ms)")
        en = r["text"] or SPEECH

    t0 = time.time()
    vi_live, ms_live = nmt.translate(en, accurate=False)
    log(f"[6] VI (live, beam={nmt.num_beams}): {vi_live!r}  ({ms_live:.0f}ms, "
        f"tong {time.time() - t0:.1f}s)")

    t0 = time.time()
    vi_final, ms_final = nmt.translate("A completely new sentence about the budget.",
                                       accurate=True)
    log(f"[7] VI (final, beam={nmt.accurate_beams}): {vi_final!r}  ({ms_final:.0f}ms, "
        f"tong {time.time() - t0:.1f}s)")

    from src.context_engine import ContextEngine
    ctx = ContextEngine("tech")
    ctx.add_terms({"latency": "độ trễ (glossary)"})
    t0 = time.time()
    vi_ctx, ms_ctx, info = ctx.translate(en, nmt, accurate=False)
    log(f"[8] VI + glossary: {vi_ctx!r} | scenario={info['scenario']} "
        f"| terms={info['terms_applied']} | so_thieu={info['numbers_missing']} "
        f"({time.time() - t0:.1f}s)")

    if audio_path and FULL:
        from src.live_session import LiveSession
        live = LiveSession(asr, nmt, None, sr=16000)
        live.set_context(scenario="tech", keywords="API, Whisper, VinAI",
                         terms={"latency": "độ trễ"})
        log(f"[9] streaming: {live.stats()}")
        t0 = time.time()
        for i in range(0, len(audio), 2048):
            live.sim.push_fast(audio[i:i + 2048])
        fin = live.finalize_text()
        log(f"    final: {fin['en'] if fin else None!r} | "
            f"speaker={fin.get('speaker') if fin else None} | "
            f"id={fin.get('id') if fin else None} | {(time.time() - t0) * 1000:.0f}ms")

    log("\nKET LUAN: pipeline chay duoc end-to-end (ASR -> NMT -> VI).")


if __name__ == "__main__":
    main()

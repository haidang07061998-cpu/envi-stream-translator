"""Gradio demo kieu Saydi, pham vi En-Vi.
Tab 1: Dich realtime (mic/upload) + scenario + custom dict + speaker + tts
Tab 2: DocTranslate | Tab 3: Tom tat + action items."""
import gradio as gr

_pipe = None
_ctx = None

def get_all(scenario="event"):
    global _pipe, _ctx
    from src.config import DEFAULT
    from src.asr import FasterWhisperASR
    from src.nmt import NMTTranslator
    from src.tts import EdgeTTSWrapper
    from src.pipeline import CascadedPipeline
    from src.context_engine import ContextEngine
    if _pipe is None:
        _pipe = CascadedPipeline(
            FasterWhisperASR(DEFAULT.asr_model, DEFAULT.asr_device, DEFAULT.asr_compute),
            NMTTranslator(DEFAULT.nmt_model, DEFAULT.nmt_src, DEFAULT.nmt_tgt),
            EdgeTTSWrapper(DEFAULT.tts_voice, DEFAULT.tts_rate))
    if _ctx is None:
        _ctx = ContextEngine(scenario)
    _ctx.set_scenario(scenario)
    return _pipe, _ctx

def run_meeting(audio_path, scenario, terms_txt, n_spk):
    import tempfile
    pipe, ctx = get_all(scenario)
    ctx.custom.clear()
    terms = {}
    for ln in (terms_txt or "").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            terms[k.strip()] = v.strip()
    if terms:
        try:
            ctx.add_terms(terms)
        except ValueError as e:
            return "", "", None, str(e), ""
    if audio_path is None:
        return "Chua co audio", "", None, "", ""
    # wrap NMT de ep thuat ngu cua context engine
    base = pipe.nmt
    class CtxNMT:
        def translate(self, t):
            if isinstance(t, list):
                outs, mss = [], 0
                for x in t:
                    vi, ms, _ = ctx.translate(x, base)
                    outs.append(vi); mss += ms
                return outs, mss
            vi, ms, _ = ctx.translate(t, base)
            return vi, ms
    real_nmt, pipe.nmt = pipe.nmt, CtxNMT()
    try:
        res = pipe.process_file(audio_path)
    finally:
        pipe.nmt = real_nmt
    from src.diarization import diarize_segments
    from src.audio_utils import load_audio_16k
    try:
        audio = load_audio_16k(audio_path)
        chunks = [audio[int(r["start"]*16000):int(r["end"]*16000)] for r in res if r.get("en")]
        labs = diarize_segments(chunks, 16000, int(n_spk)) if chunks else []
        li = 0
        for r in res:
            if r.get("en"):
                r["speaker"] = f"Speaker {labs[li]+1}" if li < len(labs) else "Speaker 1"
                li += 1
    except Exception:
        for r in res:
            r.setdefault("speaker", "Speaker 1")
    en = "\n".join(f"[{r['speaker']} {r['start']:.1f}s] {r['en']}" for r in res if r.get("en"))
    vi = "\n".join(f"[{r['speaker']} {r['start']:.1f}s] {r['vi']}" for r in res if r.get("en"))
    mp3 = None
    auds = [r["audio_vi"] for r in res if r.get("audio_vi")]
    if auds:
        mp3 = tempfile.mktemp(suffix=".mp3")
        with open(mp3, "wb") as f:
            f.write(auds[0])
    from src.metrics import latency_stats
    st = latency_stats(res)
    stat = f"mean E2E {st.get('mean_ms',0):.0f}ms | p90 {st.get('p90_ms',0):.0f}ms | scenario={scenario} terms={len(ctx.custom)}"
    full_vi = " ".join(r["vi"] for r in res if r.get("en"))
    return en or "(khong nghe thay)", vi or "(khong co ban dich)", mp3, stat, full_vi

def run_doc(f, scenario):
    if f is None:
        return None
    pipe, ctx = get_all(scenario)
    from src.doctranslate import translate_doc
    import tempfile, os
    out = tempfile.mktemp(suffix="_vi" + os.path.splitext(f)[1])
    translate_doc(f, out, translator=pipe.nmt, context=ctx)
    return out

def run_sum(vi_text):
    from src.summarizer import summarize
    r = summarize(vi_text or "")
    acts = "\n".join("- " + a for a in r.get("actions", []))
    return r.get("summary", ""), acts, r.get("engine", "")

with gr.Blocks(title="EN-VI Realtime Translator (Saydi-like)") as demo:
    gr.Markdown("# Dich hop En-Vi realtime (kieu Saydi, chi 1 cap En-Vi)")
    with gr.Tab("Hop realtime"):
        audio = gr.Audio(sources=["upload", "microphone"], type="filepath", label="Mic / upload")
        scenario = gr.Dropdown(["event", "tech", "sales", "education"], value="event", label="Scenario (AI Context)")
        terms = gr.Textbox(label="Custom Dictionary (toi da 50, moi dong: english = tieng viet)", lines=3,
                           value="keynote = bài phát biểu chính\nlatency = độ trễ")
        nspk = gr.Slider(1, 4, value=2, step=1, label="So nguoi noi (diarization)")
        btn = gr.Button("Dich")
        en_o = gr.Textbox(label="EN + speaker"); vi_o = gr.Textbox(label="VI + speaker")
        au_o = gr.Audio(label="Giong Viet"); st_o = gr.Textbox(label="Latency")
        full_vi = gr.Textbox(label="Full VI (dua sang tab Tom tat)", visible=True)
        btn.click(run_meeting, [audio, scenario, terms, nspk], [en_o, vi_o, au_o, st_o, full_vi])
    with gr.Tab("DocTranslate"):
        fi = gr.File(label="Tai docx/txt tieng Anh"); sc2 = gr.Dropdown(["event", "tech", "sales", "education"], value="event")
        b2 = gr.Button("Dich tai lieu"); fo = gr.File(label="Tai ve ban Vi")
        b2.click(run_doc, [fi, sc2], [fo])
    with gr.Tab("Tom tat"):
        ti = gr.Textbox(label="Van ban Vi", lines=6); b3 = gr.Button("Tom tat")
        so = gr.Textbox(label="Tom tat"); ao = gr.Textbox(label="Action items"); eo = gr.Textbox(label="Engine")
        b3.click(run_sum, [ti], [so, ao, eo])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", share=False)

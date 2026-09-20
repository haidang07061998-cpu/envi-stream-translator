"""Gradio demo chay duoc ca local lan Kaggle (upload file, khong phu thuoc mic).
Chay: python -m app.gradio_app  (local) | tren Kaggle: chay 2 cell trong kaggle_test.py"""
import gradio as gr

_pipe = None
def get_pipe():
    global _pipe
    if _pipe is None:
        from src.config import DEFAULT
        from src.asr import FasterWhisperASR
        from src.nmt import NMTTranslator
        from src.tts import EdgeTTSWrapper
        from src.pipeline import CascadedPipeline
        _pipe = CascadedPipeline(
            FasterWhisperASR(DEFAULT.asr_model, DEFAULT.asr_device, DEFAULT.asr_compute),
            NMTTranslator(DEFAULT.nmt_model, DEFAULT.nmt_src, DEFAULT.nmt_tgt),
            EdgeTTSWrapper(DEFAULT.tts_voice, DEFAULT.tts_rate))
    return _pipe

def run(audio_path):
    import tempfile, os
    if audio_path is None:
        return "Chua co audio", "", None, ""
    pipe = get_pipe()
    res = pipe.process_file(audio_path)
    from src.metrics import latency_stats
    st = latency_stats(res)
    en = "\n".join(f"[{r['start']:.1f}-{r['end']:.1f}s] {r['en']}" for r in res if r.get("en"))
    vi = "\n".join(f"[{r['start']:.1f}-{r['end']:.1f}s] {r['vi']}" for r in res if r.get("en"))
    # ghep audio vi dau tien de phat thu
    mp3 = None
    auds = [r["audio_vi"] for r in res if r.get("audio_vi")]
    if auds:
        mp3 = tempfile.mktemp(suffix=".mp3")
        with open(mp3, "wb") as f:
            f.write(auds[0])
    stat = f"mean E2E {st.get('mean_ms',0):.0f}ms | p90 {st.get('p90_ms',0):.0f}ms | ASR {st.get('mean_asr',0):.0f} / NMT {st.get('mean_nmt',0):.0f} / TTS {st.get('mean_tts',0):.0f}ms"
    return en or "(khong nghe thay tieng noi)", vi or "(khong co ban dich)", mp3, stat

demo = gr.Interface(fn=run,
    inputs=gr.Audio(sources=["upload","microphone"], type="filepath", label="Noi tieng Anh vao mic / upload wav 16kHz"),
    outputs=[gr.Textbox(label="EN transcript (live caption)"), gr.Textbox(label="VI dich"),
             gr.Audio(label="Giong doc Tieng Viet (doan 1)"), gr.Textbox(label="Latency")],
    title="Dich thuat giong noi Anh-Viet realtime (Cascaded: Whisper + NLLB + Edge-TTS)")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", share=False)

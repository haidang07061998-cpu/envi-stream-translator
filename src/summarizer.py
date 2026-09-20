"""Tom tat + action items tieng Viet sau buoi hop (kieu Saydi / NoteX).

- Uu tien LLM neu co GROQ_API_KEY / OPENAI_API_KEY
- Fallback: trich rut offline (khong can mang, khong lot du lieu)
- `mode`: minutes | actions | custom  (tuong duong "Custom AI Commands" cua Saydi)

Sua loi ban cu: server cu `os.environ.pop` API key ngay trong request -> tat LLM
VINH VIEN cho ca process. Gio chi KIEM TRA co `offline`/`confidential` khi goi,
khong bao gio sua bien moi truong.
"""
import os
import re

from .config import DEFAULT


def _split_vi(text):
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


_ACTION_RE = re.compile(
    r"\b(cần|phải|sẽ|hãy|nên|deadline|hoàn thành|gửi|chuẩn bị|liên hệ|"
    r"chịu trách nhiệm|thống nhất|theo dõi|kiểm tra|xác nhận)\b", re.I)


def extract_actions(vi_text, limit=5):
    return [s for s in _split_vi(vi_text) if _ACTION_RE.search(s)][:limit]


def extractive_summary(vi_text, max_sent=5):
    sents = _split_vi(vi_text)
    if len(sents) <= max_sent:
        return sents, extract_actions(vi_text)
    freq = {}
    for s in sents:
        for w in re.findall(r"\w+", s.lower()):
            freq[w] = freq.get(w, 0) + 1
    scored = sorted(sents, key=lambda s: sum(freq.get(w, 0)
                                             for w in re.findall(r"\w+", s.lower())),
                    reverse=True)
    summ = sorted(scored[:max_sent], key=sents.index)
    return summ, extract_actions(vi_text)


def _llm_available():
    """Che do mat/offline: KHONG BAO GIO goi cloud (khong doi bien moi truong)."""
    if DEFAULT.offline or DEFAULT.confidential:
        return None
    return os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")


_PROMPTS = {
    "minutes": ("Tóm tắt ngắn gọn nội dung cuộc họp sau bằng tiếng Việt (5 gạch đầu dòng), "
                "giữ đúng số liệu và tên riêng. Nội dung:\n"),
    "actions": ("Từ nội dung cuộc họp sau, liệt kê Action items bằng tiếng Việt "
                "(mỗi dòng: việc cần làm - người phụ trách nếu có - thời hạn nếu có). "
                "Nội dung:\n"),
    "custom": ("Nội dung:\n"),
}


def summarize(vi_text, max_sent=5, mode="minutes", prompt=None):
    """Tra ve {"summary", "actions", "engine", "mode"}."""
    vi_text = (vi_text or "").strip()
    mode = mode if mode in _PROMPTS else "minutes"
    key = _llm_available()
    if key and vi_text:
        try:
            from openai import OpenAI
            base = os.getenv("OPENAI_BASE_URL") or (
                "https://api.groq.com/openai/v1" if os.getenv("GROQ_API_KEY") else None)
            cli = OpenAI(api_key=key, base_url=base) if base else OpenAI(api_key=key)
            model = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
            instruction = prompt if (mode == "custom" and prompt) else _PROMPTS[mode]
            r = cli.chat.completions.create(
                model=model, temperature=0.2,
                messages=[{"role": "user", "content": instruction + vi_text[:6000]}])
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                return {"summary": txt,
                        "actions": [] if mode != "minutes" else extract_actions(vi_text),
                        "engine": f"llm:{model}", "mode": mode}
        except Exception as e:
            print("[summarizer] LLM loi, fallback offline:", e)

    s, a = extractive_summary(vi_text, max_sent)
    if mode == "actions":
        body = "\n".join("- " + x for x in a) or "(khong tim thay action item)"
        return {"summary": body, "actions": a, "engine": "offline-extractive",
                "mode": mode}
    return {"summary": "\n".join("- " + x for x in s), "actions": a,
            "engine": "offline-extractive", "mode": mode}

"""AI Context Engine (kieu Saydi), pham vi EN -> VI.

Gom 3 thu Saydi co:
1. Scenario Gallery    : preset Tech / Sales / Event / Education
2. Meeting Details & Keywords : nap ten rieng, thuat ngu -> dua vao ASR initial_prompt
                                (giup Whisper viet dung ten/ jargon ngay tu dau)
3. Custom Dictionary   : toi da `max_terms` (mac dinh 50) thuat ngu EN->VI, ep sau NMT

Sua loi ban cu:
- `preset_terms` cua SCENARIOS truoc day KHONG BAO GIO duoc ap dung (chi custom duoc
  build pattern) -> Scenario Gallery chi la trang tri. Gio `glossary()` gop ca hai.
- `_protect_numbers` tinh `missing` roi `return vi_text` (code chet). Gio bao cao
  so bi thieu trong `info` de con nguoi doi chieu, khong tu sua bay.
"""
import re
from .config import DEFAULT

SCENARIOS = {
    "tech": {"name": "Cong nghe / Ky thuat",
             "hint": "Uu tien thuat ngu cong nghe, giu nguyen ten rieng, API, model.",
             "preset_terms": {"machine learning": "học máy", "streaming": "phát trực tuyến",
                              "latency": "độ trễ", "pipeline": "luồng xử lý",
                              "deployment": "triển khai", "dataset": "tập dữ liệu"}},
    "sales": {"name": "Kinh doanh / Dam phan",
              "hint": "Giong lich su, ro rang, giu so lieu, ten cong ty.",
              "preset_terms": {"deal": "thương vụ", "stakeholder": "bên liên quan",
                               "revenue": "doanh thu", "discount": "chiết khấu"}},
    "event": {"name": "Hoi thao / Su kien",
              "hint": "Cau ngan, de nghe, de hien thi caption.",
              "preset_terms": {"keynote": "bài phát biểu chính", "panel": "phiên thảo luận",
                               "agenda": "chương trình nghị sự"}},
    "education": {"name": "Bai giang / Dao tao",
                  "hint": "Dien dat su pham, de hieu.",
                  "preset_terms": {"assignment": "bài tập", "syllabus": "đề cương môn học",
                                   "lecture": "bài giảng"}},
}

SCENARIO_KEYWORDS = {
    "tech": ["model", "api", "server", "latency", "pipeline", "whisper", "neural",
             "dataset", "software", "deploy", "cloud", "algorithm", "streaming",
             "artificial intelligence", "machine learning", "sensor", "robot"],
    "sales": ["deal", "contract", "price", "discount", "client", "revenue",
              "stakeholder", "negotiat", "offer", "payment", "budget", "sales", "customer"],
    "education": ["lesson", "assignment", "syllabus", "student", "teacher", "exam",
                  "homework", "lecture", "course", "class", "learn", "study"],
    "event": ["keynote", "panel", "welcome", "conference", "audience", "stage",
              "session", "speaker", "ceremony", "guest"],
}


def detect_scenario(text):
    """Tu nhan ngu canh tu cau tieng Anh. Tra ve (scenario, diem)."""
    t = " " + (text or "").lower() + " "
    best, score = "event", 0
    for sc, words in SCENARIO_KEYWORDS.items():
        s = 0
        for w in words:
            if " " in w:
                if w in t:
                    s += 1
            elif re.search(rf"\b{re.escape(w)}\b", t):
                s += 1
        if s > score:
            best, score = sc, s
    return best, score


class ContextEngine:
    def __init__(self, scenario="event", auto=True, max_terms=None):
        self.scenario = scenario if scenario in SCENARIOS else "event"
        self.auto = auto
        self.max_terms = int(max_terms if max_terms is not None
                             else DEFAULT.glossary_max_terms)
        self.details = ""
        self.keywords = []
        self.custom = {}          # en_lower -> vi (do nguoi dung nhap)
        self._votes = {s: 0 for s in SCENARIOS}
        self._patterns = []       # [(compiled, vi)] build tu glossary()
        self._rebuild_patterns()

    # ------------------------------------------------------------ cau hinh phien
    def set_scenario(self, s):
        if s in SCENARIOS:
            self.scenario = s
            self._rebuild_patterns()
        return self.scenario

    def set_meeting(self, details="", keywords=None):
        """Nap boi canh truoc gio dich (Saydi: Meeting Details & Keywords)."""
        self.details = (details or "").strip()
        if keywords is None:
            self.keywords = []
        elif isinstance(keywords, str):
            self.keywords = [k.strip() for k in re.split(r"[,\n;]+", keywords) if k.strip()]
        else:
            self.keywords = [str(k).strip() for k in keywords if str(k).strip()]
        return self

    def asr_prompt(self):
        """Prompt tieng Anh nap vao Whisper de viet dung ten rieng / thuat ngu."""
        bits = []
        if self.keywords:
            bits.append("Names and terms: " + ", ".join(self.keywords[:25]) + ".")
        if self.details:
            d = " ".join(self.details.split())
            bits.append(d[:180])
        if not bits:
            return None
        return (" ".join(bits))[:240]

    # ------------------------------------------------------------ Custom Dictionary
    def add_terms(self, terms: dict):
        """terms: {en: vi}. Vuot `max_terms` -> ValueError (giong Saydi: toi da 50)."""
        for k, v in (terms or {}).items():
            k = (k or "").strip()
            v = (v or "").strip()
            if not k or not v:
                continue
            if len(self.custom) >= self.max_terms and k.lower() not in self.custom:
                raise ValueError(
                    f"Custom Dictionary toi da {self.max_terms} thuat ngu")
            self.custom[k.lower()] = v
        self._rebuild_patterns()
        return self.custom

    def remove_term(self, en):
        self.custom.pop((en or "").lower(), None)
        self._rebuild_patterns()

    def clear_custom(self):
        self.custom.clear()
        self._rebuild_patterns()

    def export_terms(self):
        return dict(self.custom)

    def glossary(self):
        """Gop preset cua scenario + custom (custom thang)."""
        d = dict(SCENARIOS[self.scenario].get("preset_terms", {}))
        d.update(self.custom)
        return d

    def _rebuild_patterns(self):
        self._patterns = []
        for en, vi in sorted(self.glossary().items(), key=lambda x: -len(x[0])):
            try:
                pat = re.compile(rf"\b{re.escape(en)}\b", re.IGNORECASE)
                self._patterns.append((pat, vi))
            except Exception:
                continue

    def _enforce_terms(self, vi_text: str) -> str:
        """Thay hau NMT: neu ban dich con giu tu EN thi ep sang thuat ngu VI."""
        out = vi_text
        for pat, vi in self._patterns:
            if pat.search(out):
                out = pat.sub(vi, out)
        return out

    @staticmethod
    def _missing_numbers(en_text: str, vi_text: str):
        """Bao cao so co trong EN nhung mat trong VI (khong tu chen -> tranh sai ngu phap)."""
        try:
            en_nums = re.findall(r"\d+(?:[.,]\d+)*", en_text or "")
            if not en_nums:
                return []
            vi_nums = set(re.findall(r"\d+(?:[.,]\d+)*", vi_text or ""))
            flat = {v.replace(",", "").replace(".", "") for v in vi_nums}
            return [n for n in en_nums
                    if n not in vi_nums and n.replace(",", "").replace(".", "") not in flat]
        except Exception:
            return []

    # ------------------------------------------------------------ ngu canh tu dong
    def auto_update(self, en_text):
        """Tu nhan ngu canh theo tung cau + decay de khong ket scenario cu."""
        if not self.auto:
            return self.scenario
        for k in self._votes:
            self._votes[k] *= 0.95
        sc, score = detect_scenario(en_text)
        if score > 0:
            self._votes[sc] += score
            top = max(self._votes, key=self._votes.get)
            if top != self.scenario and self._votes[top] >= self._votes[self.scenario] + 2:
                self.scenario = top
                self._rebuild_patterns()
        return self.scenario

    # ------------------------------------------------------------ dich
    def translate(self, en_text: str, base_translator, use_beams=None, accurate: bool = True):
        """Dich qua NMT goc roi ep thuat ngu + ghi nhan ngu canh.

        Tra ve (vi, ms, info) voi info = {scenario, terms_applied, numbers_missing}.
        """
        en_text = (en_text or "").strip()
        if not en_text:
            return "", 0.0, {"scenario": self.scenario, "terms_applied": 0,
                             "numbers_missing": []}
        self.auto_update(en_text)
        try:
            vi, ms = base_translator.translate(en_text, accurate=accurate)
        except TypeError:
            vi, ms = base_translator.translate(en_text)
        vi = self._enforce_terms(vi)
        info = {"scenario": self.scenario,
                "terms_applied": len(self.glossary()),
                "numbers_missing": self._missing_numbers(en_text, vi)}
        return vi, ms, info

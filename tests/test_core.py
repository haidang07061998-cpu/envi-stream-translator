"""Test cho phan loi thuan (khong can model, khong can mang).

Chay: python -m unittest discover -s tests -v

Moi test o day tuong ung 1 loi da phat hien trong ban cu -> test nay la bang chung
loi da duoc sua va khong tai phat.
"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import rooms                                    # noqa: E402
from src.config import AppConfig, DEFAULT                # noqa: E402
from src.context_engine import ContextEngine             # noqa: E402
from src import diarization as dz                        # noqa: E402
from src.metrics import latency_stats                    # noqa: E402
from src.simultaneous import (SimultaneousProcessor, _clean_en,  # noqa: E402
                              strip_overlap)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------- fakes
class FakeASR:
    def __init__(self, texts=()):
        self.texts = list(texts)
        self.calls = 0
        self.prompt = None
        self.gate_rms = 0.004

    def transcribe(self, audio, sr=16000, initial_prompt=None):
        self.calls += 1
        return {"text": self.texts.pop(0) if self.texts else "", "asr_ms": 1.0}

    def set_prompt(self, p):
        self.prompt = p


class FakeNMT:
    def __init__(self):
        self.calls = 0
        self.glossary = None

    def translate(self, text, accurate=False):
        self.calls += 1
        return ("VI:" + text, 1.0)

    def set_glossary(self, terms):
        self.glossary = terms


def loud(sec=1.0, sr=16000, seed=0):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(sec * sr)) * 0.3).astype(np.float32)


# --------------------------------------------------------------------- 1. loc hallucination
class TestCleanEn(unittest.TestCase):
    def test_giu_cau_bat_dau_bang_you(self):
        """LOI CU: startswith('you ') -> xoa trang moi cau bat dau bang 'You ...'."""
        for s in ["You should check the API latency",
                  "You can see the results here",
                  "You know what I mean",
                  "Yes, that is correct",
                  "No, we cannot do that",
                  "Okay let us start the meeting"]:
            self.assertEqual(_clean_en(s), s, f"bi xoa oan: {s}")

    def test_bo_hallucination_dung_nghia(self):
        for s in ["Thank you for watching", "thanks for watching!",
                  "Please subscribe", "Subtitles by Amara.org", "Music"]:
            self.assertEqual(_clean_en(s), "", f"phai bi loc: {s}")

    def test_bo_token_nhieu_don_le(self):
        for s in ["you", "Uh", "hmm.", "um"]:
            self.assertEqual(_clean_en(s), "", f"phai bi loc: {s}")

    def test_bo_cau_lap_tu(self):
        self.assertEqual(_clean_en("you you you you"), "")
        self.assertEqual(_clean_en("the the the the the the"), "")

    def test_giu_cau_ngan_co_nghia(self):
        for s in ["Yes", "No", "Okay", "Thanks"]:
            self.assertEqual(_clean_en(s), s, f"cau ngan co nghia bi xoa: {s}")

    def test_rong(self):
        self.assertEqual(_clean_en(""), "")
        self.assertEqual(_clean_en(None), "")


# --------------------------------------------------------------------- 2. chong lap tu
class TestStripOverlap(unittest.TestCase):
    def test_cat_duoi_trung(self):
        self.assertEqual(strip_overlap("the latency is too high",
                                       "too high for mobile clients"),
                         "for mobile clients")

    def test_khong_trung_thi_giu_nguyen(self):
        self.assertEqual(strip_overlap("hello world", "completely new sentence"),
                         "completely new sentence")

    def test_prev_rong(self):
        self.assertEqual(strip_overlap("", "abc"), "abc")

    def test_cat_ca_cau_trung(self):
        self.assertEqual(strip_overlap("we ship today", "we ship today"), "")


# --------------------------------------------------------------------- 3. streaming
class TestSimultaneous(unittest.TestCase):
    def _proc(self, texts, mode="translate"):
        asr = FakeASR(texts)
        nmt = FakeNMT()
        p = SimultaneousProcessor(asr, nmt, None, 16000, partial_every_sec=0.0,
                                  mode=mode)
        return p, asr, nmt

    def test_gate_im_lang_khong_goi_asr(self):
        """LOI CU: push() khong co gate -> chay ASR ca khi im lang (ton CPU + bia chu)."""
        p, asr, _ = self._proc([])
        for _ in range(10):
            self.assertIsNone(p.push(np.zeros(4000, dtype=np.float32)))
        self.assertEqual(asr.calls, 0, "im lang ma van goi ASR")

    def test_co_tieng_thi_goi_asr(self):
        p, asr, _ = self._proc(["hello world"])
        ev = p.push(loud(0.5))
        self.assertIsNotNone(ev)
        self.assertEqual(ev["en"], "hello world")
        self.assertEqual(asr.calls, 1)

    def test_finalize_cat_overlap(self):
        """LOI CU: finalize_fast giu 0.8s duoi -> lap tu o dau cau."""
        p, asr, _ = self._proc(["the latency is too high",
                                "too high for mobile clients"])
        # nap buffer truc tiep (khong qua push) de ASR chi duoc goi luc finalize
        p._push_buf(loud(1.0))
        f1 = p.finalize_text()
        self.assertEqual(f1["en"], "the latency is too high")
        p._push_buf(loud(1.0, seed=1))
        f2 = p.finalize_text()
        self.assertEqual(f2["en"], "for mobile clients", "chua cat phan overlap")

    def test_transcribe_mode_khong_dich(self):
        p, _, nmt = self._proc(["hello"], mode="transcribe")
        ev = p.push(loud(0.5))
        self.assertIsNotNone(ev)
        self.assertIsNone(ev["vi"])
        self.assertEqual(nmt.calls, 0)

    def test_buffer_co_tran(self):
        p, _, _ = self._proc([])
        for _ in range(30):
            p.push(np.ones(16000, dtype=np.float32) * 0.5)
        self.assertLessEqual(len(p.buf), p.maxn)


# --------------------------------------------------------------------- 4. context engine
class TestContextEngine(unittest.TestCase):
    def test_preset_scenario_duoc_ap_dung(self):
        """LOI CU: preset_terms cua SCENARIOS khong bao gio duoc build pattern."""
        ctx = ContextEngine("tech")
        out = ctx._enforce_terms("The latency of this pipeline is high")
        self.assertIn("độ trễ", out)
        self.assertIn("luồng xử lý", out)

    def test_custom_dictionary_ghi_de_preset(self):
        ctx = ContextEngine("tech")
        ctx.add_terms({"latency": "độ trễ mạng"})
        self.assertIn("độ trễ mạng", ctx._enforce_terms("latency"))

    def test_gioi_han_50_thuat_ngu(self):
        ctx = ContextEngine("event", max_terms=3)
        ctx.add_terms({"a": "1", "b": "2", "c": "3"})
        with self.assertRaises(ValueError):
            ctx.add_terms({"d": "4"})
        ctx.add_terms({"a": "1 moi"})     # cap nhat term da co thi khong tinh them

    def test_meeting_keywords_vao_asr_prompt(self):
        ctx = ContextEngine("event")
        ctx.set_meeting(details="Kickoff voi doi tac Nhat",
                        keywords="Whisper, VinAI, SotaTek")
        prompt = ctx.asr_prompt()
        self.assertIsNotNone(prompt)
        self.assertIn("Whisper", prompt)
        self.assertIn("SotaTek", prompt)

    def test_asr_prompt_rong_khi_khong_co_gi(self):
        self.assertIsNone(ContextEngine("event").asr_prompt())

    def test_detect_scenario(self):
        from src.context_engine import detect_scenario
        self.assertEqual(detect_scenario("we deploy the model to cloud")[0], "tech")
        self.assertEqual(detect_scenario("the price and contract for this client")[0], "sales")

    def test_bao_so_bi_thieu_khong_tu_sua(self):
        ctx = ContextEngine("event")
        vi, ms, info = ctx.translate("We have 25 servers", FakeNMT())
        self.assertEqual(vi, "VI:We have 25 servers")
        self.assertEqual(info["numbers_missing"], [])

    def test_dich_rong(self):
        ctx = ContextEngine("event")
        vi, ms, info = ctx.translate("   ", FakeNMT())
        self.assertEqual(vi, "")


# --------------------------------------------------------------------- 5. diarization on dinh
class TestSpeakerTracker(unittest.TestCase):
    def setUp(self):
        self.orig = dz._mfcc_mean

    def tearDown(self):
        dz._mfcc_mean = self.orig

    def _fake(self, vec):
        dz._mfcc_mean = lambda audio, sr=16000, n_mfcc=13: np.asarray(vec, dtype=np.float32)

    def test_nhan_on_dinh_khong_hoan_vai(self):
        """LOI CU: KMeans fit lai moi cau -> 'Speaker 1/2' hoan vai giua cac cau."""
        tr = dz.SpeakerTracker(max_k=4, threshold=0.6)
        a = np.zeros(16000, dtype=np.float32)
        va = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        va2 = [0.9, 0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        vb = [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0]

        self._fake(va)
        self.assertEqual(tr.assign(a)[0], 0)
        self._fake(va2)
        self.assertEqual(tr.assign(a)[0], 0, "cung nguoi nhung bi doi nhan")
        self.assertEqual(tr.n_speakers, 1)

        self._fake(vb)
        lab_b, k = tr.assign(a)
        self.assertEqual(k, 2)
        self.assertEqual(lab_b, 1)

        self._fake(va)                      # quay lai nguoi dau -> PHAI van la 0
        self.assertEqual(tr.assign(a)[0], 0, "nhan nguoi noi bi hoan vai")

    def test_audio_qua_ngan(self):
        tr = dz.SpeakerTracker()
        self.assertEqual(tr.assign(np.zeros(10, dtype=np.float32))[1], 1)

    def test_khong_co_code_gia_ngau_nhien(self):
        """LOI CU: label_speakers sinh dac trung bang np.random.randn -> nhan ngau nhien."""
        self.assertFalse(hasattr(dz, "label_speakers"))


# --------------------------------------------------------------------- 6. rooms / phong
class TestRooms(unittest.TestCase):
    def setUp(self):
        rooms.SESSIONS.clear()
        rooms._LISTENERS.clear()
        os.environ.pop("REDIS_URL", None)

    def tearDown(self):
        rooms.SESSIONS.clear()
        rooms._LISTENERS.clear()

    def test_pin_luu_hash_khong_luu_plaintext(self):
        sid = rooms.create_session("hop mat", pin="1234")
        s = rooms.get_session(sid)
        self.assertNotIn("1234", json.dumps(s, ensure_ascii=False))
        self.assertTrue(rooms.check_pin(sid, "1234"))
        self.assertFalse(rooms.check_pin(sid, "0000"))
        self.assertFalse(rooms.check_pin(sid, ""))

    def test_phong_khong_pin_thi_luon_mo(self):
        sid = rooms.create_session("mo")
        self.assertTrue(rooms.check_pin(sid, ""))
        self.assertTrue(rooms.check_pin(sid, "bat ky"))

    def test_caption_id_tang_dan_va_lay_theo_since(self):
        sid = rooms.create_session("t")
        for i in range(5):
            rooms.add_caption(sid, f"en {i}", f"vi {i}")
        caps = rooms.get_captions(sid, 0)
        self.assertEqual([c["id"] for c in caps], [1, 2, 3, 4, 5])
        self.assertEqual(len(rooms.get_captions(sid, 3)), 2)

    def test_tran_so_caption(self):
        old = rooms._MAX_CAP
        rooms._MAX_CAP = 3
        try:
            sid = rooms.create_session("t")
            for i in range(6):
                rooms.add_caption(sid, f"en {i}")
            caps = rooms.get_captions(sid, 0)
            self.assertEqual(len(caps), 3)
            self.assertEqual(caps[-1]["en"], "en 5")
        finally:
            rooms._MAX_CAP = old

    def test_srt_dung_thoi_gian_that(self):
        """LOI CU: SRT bia moi cue 3.0s noi tiep -> lech hoan toan voi audio."""
        sid = rooms.create_session("t")
        rooms.add_caption(sid, "a", "cau mot", t_start=100.0, t_end=102.5)
        rooms.add_caption(sid, "b", "cau hai", t_start=110.0, t_end=113.0)
        srt = rooms.export_session_srt(sid)
        lines = [ln for ln in srt.splitlines() if "-->" in ln]
        self.assertEqual(lines[0], "00:00:00,000 --> 00:00:02,500")
        self.assertEqual(lines[1], "00:00:10,000 --> 00:00:13,000")

    def test_vtt_co_header(self):
        sid = rooms.create_session("t")
        rooms.add_caption(sid, "a", "xin chao", t_start=1.0, t_end=2.0)
        vtt = rooms.export_session_vtt(sid)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("-->", vtt)
        self.assertIn(".", vtt.split("-->")[1].split("\n")[0])

    def test_export_txt_cac_mode(self):
        sid = rooms.create_session("Chu de A")
        rooms.add_caption(sid, "hello", "xin chao")
        both = rooms.export_session_txt(sid, "both")
        self.assertIn("EN: hello", both)
        self.assertIn("VI: xin chao", both)
        self.assertIn("FULL TIENG VIET", both)
        self.assertIn("hello", rooms.export_session_txt(sid, "en"))
        self.assertNotIn("EN: hello", rooms.export_session_txt(sid, "vi"))

    def test_phong_khong_ton_tai(self):
        self.assertIsNone(rooms.export_session_txt("khongco"))
        self.assertIsNone(rooms.get_session("khongco"))
        self.assertIsNone(rooms.add_caption("khongco", "x"))

    def test_xoa_phong(self):
        sid = rooms.create_session("t")
        rooms.add_caption(sid, "a")
        rooms.delete_session(sid)
        self.assertIsNone(rooms.get_session(sid))
        self.assertEqual(rooms.get_captions(sid, 0), [])

    def test_het_han_duoc_don(self):
        """LOI CU: phong RAM khong bao gio het han -> phinh RAM."""
        sid = rooms.create_session("t", ttl_hours=0.0001)
        rooms.SESSIONS[sid]["expires"] = 1.0        # qua khu
        dead = rooms.sweep_expired(now=2.0)
        self.assertIn(sid, dead)
        self.assertIsNone(rooms.get_session(sid))

    def test_subscribe_nhan_caption_realtime(self):
        """Tinh nang moi: day caption realtime thay vi client poll 1s/lan."""
        sid = rooms.create_session("t")
        got = []
        cb = rooms.subscribe(sid, got.append)
        rooms.add_caption(sid, "en", "vi")
        rooms.unsubscribe(sid, cb)
        rooms.add_caption(sid, "en2", "vi2")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["en"], "en")

    def test_cap_nhat_ban_dich_sau(self):
        sid = rooms.create_session("t")
        cap = rooms.add_caption(sid, "en", None)
        rooms.update_caption(sid, cap["id"], vi="ban dich", nmt_ms=12.5, t_end=5.0)
        c = rooms.get_captions(sid, 0)[0]
        self.assertEqual(c["vi"], "ban dich")
        self.assertEqual(c["nmt_ms"], 12.5)

    def test_link_va_qr_khong_vo_khi_thieu_thu_vien(self):
        sid = rooms.create_session("t")
        link = rooms.session_link(sid, "http://localhost:8000")
        self.assertTrue(link.endswith(f"/room/{sid}"))
        qr = rooms.session_qr(sid, "http://localhost:8000")
        self.assertTrue(qr.startswith("data:image/png;base64,") or qr == link)


# --------------------------------------------------------------------- 7. config
class TestConfig(unittest.TestCase):
    def test_env_ghi_de(self):
        with mock.patch.dict(os.environ, {"PARTIAL_EVERY": "0.3",
                                          "FINAL_SILENCE": "0.4",
                                          "MODE": "transcribe"}, clear=False):
            c = AppConfig()
        self.assertAlmostEqual(c.partial_every_sec, 0.3)
        self.assertAlmostEqual(c.final_silence_sec, 0.4)
        self.assertEqual(c.mode, "transcribe")

    def test_mode_la_luon_bi_chan(self):
        with mock.patch.dict(os.environ, {"MODE": "two-way"}, clear=False):
            self.assertEqual(AppConfig().mode, "translate")

    def test_offline_ep_tts_offline(self):
        with mock.patch.dict(os.environ, {"OFFLINE": "1", "TTS_ENGINE": "edge"},
                             clear=False):
            c = AppConfig()
        self.assertTrue(c.offline)
        self.assertEqual(c.tts_engine, "offline")

    def test_confidential_ep_offline(self):
        with mock.patch.dict(os.environ, {"CONFIDENTIAL": "1"}, clear=False):
            c = AppConfig()
        self.assertTrue(c.offline)
        self.assertTrue(c.confidential)

    def test_chon_model_theo_gpu(self):
        """LOI CU: desktop tu set ASR_MODEL=tiny.en -> may co GPU van chay model nho."""
        env = {k: v for k, v in os.environ.items() if k != "ASR_MODEL"}
        with mock.patch.dict(os.environ, env, clear=True):
            c = AppConfig()
            self.assertEqual(c.resolve_asr_model(True), c.asr_model)
            self.assertEqual(c.resolve_asr_model(False), c.asr_model_offline)
        with mock.patch.dict(os.environ, {"ASR_MODEL": "small.en"}, clear=False):
            self.assertEqual(AppConfig().resolve_asr_model(True), "small.en")

    def test_final_beams(self):
        c = AppConfig()
        self.assertEqual(c.resolve_final_beams(True), 4)
        self.assertEqual(c.resolve_final_beams(False), 2)


# --------------------------------------------------------------------- 8. metrics
class TestMetrics(unittest.TestCase):
    def test_latency_stats(self):
        rows = [{"en": "a", "e2e_ms": 1000, "asr_ms": 300, "nmt_ms": 400,
                 "tts_ms": 200, "start": 0, "end": 2},
                {"en": "b", "e2e_ms": 3000, "asr_ms": 500, "nmt_ms": 600,
                 "tts_ms": 200, "start": 2, "end": 4}]
        st = latency_stats(rows, target_sec=2.0)
        self.assertEqual(st["n"], 2)
        self.assertAlmostEqual(st["mean_ms"], 2000)
        self.assertAlmostEqual(st["realtime_ok_ratio"], 0.5)
        self.assertAlmostEqual(st["rtf"], 4.0 / 4.0)
        self.assertIn("asr", st)

    def test_rong(self):
        self.assertEqual(latency_stats([]), {})
        self.assertEqual(latency_stats([{"en": ""}]), {})


# --------------------------------------------------------------------- 9. summarizer
class TestSummarizer(unittest.TestCase):
    def test_offline_khong_goi_llm(self):
        from src.summarizer import summarize
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "fake"}, clear=False), \
             mock.patch.object(DEFAULT, "offline", True):
            r = summarize("Chung ta can gui bao cao. Cuoc hop rat tot.")
        self.assertEqual(r["engine"], "offline-extractive")

    def test_trich_action_items(self):
        from src.summarizer import extract_actions
        acts = extract_actions("Anh Nam sẽ gửi báo cáo. Trời hôm nay đẹp. "
                              "Chị Lan cần chuẩn bị tài liệu.")
        self.assertEqual(len(acts), 2)

    def test_mode_actions(self):
        from src.summarizer import summarize
        r = summarize("Chúng ta cần kiểm tra lại API.", mode="actions")
        self.assertEqual(r["mode"], "actions")


# --------------------------------------------------------------------- 10. client JS/JSON
class TestClientAssets(unittest.TestCase):
    """Loi that da tung lam PWA mobile chet hoan toan: dau '|' lac trong <script>."""

    @staticmethod
    def _node():
        return shutil.which("node")

    def _parse_inline_scripts(self, rel):
        node = self._node()
        if not node:
            self.skipTest("khong co node")
        path = os.path.join(ROOT, rel)
        with open(path, encoding="utf-8") as f:
            html = f.read()
        self.assertNotIn("|};", html, "con dau '|' lac trong script")
        import re
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertTrue(scripts, "khong tim thay <script>")
        for i, s in enumerate(scripts):
            js = os.path.join(ROOT, "_t_check.js")
            with open(js, "w", encoding="utf-8") as f:
                f.write(s)
            try:
                r = subprocess.run([node, "--check", js], capture_output=True, text=True)
            finally:
                try:
                    os.remove(js)
                except OSError:
                    pass
            self.assertEqual(r.returncode, 0, f"{rel} script #{i} loi: {r.stderr[:400]}")

    def test_mobile_pwa_script_parse_duoc(self):
        self._parse_inline_scripts(os.path.join("static", "mobile", "index.html"))

    def test_room_page_script_parse_duoc(self):
        self._parse_inline_scripts(os.path.join("static", "room", "index.html"))

    def test_mobile_manifest_json_hop_le(self):
        p = os.path.join(ROOT, "static", "mobile", "manifest.json")
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("name", data)
        self.assertIn("start_url", data)

    def test_extension_manifest_hop_le_va_du_file(self):
        p = os.path.join(ROOT, "extension", "manifest.json")
        if not os.path.exists(p):
            self.skipTest("chua co extension")
        with open(p, encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m.get("manifest_version"), 3)
        refs = []
        popup = (m.get("action") or {}).get("default_popup")
        if popup:
            refs.append(popup)
        bg = (m.get("background") or {}).get("service_worker")
        if bg:
            refs.append(bg)
        for r in refs:
            self.assertTrue(os.path.exists(os.path.join(ROOT, "extension", r)),
                            f"manifest tro toi file khong ton tai: {r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

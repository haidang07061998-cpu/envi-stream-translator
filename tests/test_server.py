"""Test tich hop HTTP/WS cho app.server (KHONG tai model).

Dung TestClient KHONG qua context manager -> lifespan khong chay -> khong keo
Whisper/VinAI ve. Nho vay test chay trong ~1 giay va kiem chung duoc:
routing, phan quyen PIN, export TXT/SRT/VTT, tom tat, WS room, va ca nhanh tu choi
cua WS stream (phong sai / sai PIN) - nhanh nay xay ra TRUOC khi tai model.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient      # noqa: E402

from app import server                          # noqa: E402
from src import rooms                           # noqa: E402

# KHONG dung `with TestClient(...)` -> khong chay lifespan -> khong tai model
client = TestClient(server.app)


class TestServerHttp(unittest.TestCase):
    def setUp(self):
        rooms.SESSIONS.clear()
        rooms._LISTENERS.clear()
        server.LIVE_CONTEXT.clear()
        os.environ.pop("REDIS_URL", None)

    def tearDown(self):
        rooms.SESSIONS.clear()
        rooms._LISTENERS.clear()
        server.LIVE_CONTEXT.clear()

    # ---------------------------------------------------------------- meta
    def test_health(self):
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        for k in ("loaded", "loading", "offline", "confidential", "tts", "asr",
                  "mode", "partial_every", "glossary_terms", "rooms"):
            self.assertIn(k, j)
        self.assertFalse(j["loaded"], "test nay khong duoc tai model")

    def test_metrics(self):
        r = client.get("/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("latency_ms", r.json())

    # ---------------------------------------------------------------- pages
    def test_mobile_page(self):
        r = client.get("/m")
        self.assertEqual(r.status_code, 200)
        # PWA dung tieng Viet co dau: "BẬT MIC"; id trong HTML la camelCase
        self.assertIn("B\u1eacT MIC", r.text)
        self.assertIn('id="liveEn"', r.text)
        self.assertIn('id="liveVi"', r.text)
        self.assertIn("/ws/stream", r.text)

    def test_room_page(self):
        sid = rooms.create_session("t")
        r = client.get(f"/room/{sid}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("MAN HINH 1", r.text)

    def test_service_worker_header(self):
        r = client.get("/static/mobile/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("service-worker-allowed"), "/")

    # ---------------------------------------------------------------- QR / link
    def test_qr_dung_host_tu_request_khi_khong_co_server_host(self):
        """LOI THAT: khong dat SERVER_HOST (kieu Kaggle/Colab) -> link/QR tro vao
        localhost:8000 -> dien thoai quet xong mo localhost CUA CHINH NO, khong vao duoc.
        Phai lay host tu chinh request dang goi.
        """
        env = {k: v for k, v in os.environ.items() if k != "SERVER_HOST"}
        with mock.patch.dict(os.environ, env, clear=True):
            j = client.post("/session/create", data={"topic": "t"}).json()
            self.assertIn("testserver", j["link"],
                          "phai dung host cua request, khong phai localhost:8000")
            self.assertTrue(j["link"].endswith("/room/" + j["sid"]))

    def test_server_host_duoc_uu_tien(self):
        """Cac file .bat dat SERVER_HOST=http://<IP-LAN>:8000 -> QR phai dung IP LAN
        (de dien thoai khac trong WiFi quet duoc, du nguoi mo trang la localhost)."""
        with mock.patch.dict(os.environ, {"SERVER_HOST": "http://192.168.1.2:8000"},
                             clear=False):
            j = client.post("/session/create", data={"topic": "t"}).json()
            self.assertTrue(j["link"].startswith("http://192.168.1.2:8000/room/"))

    def test_qr_png_tra_anh_that(self):
        sid = client.post("/session/create", data={"topic": "t"}).json()["sid"]
        r = client.get(f"/session/{sid}/qr.png")
        self.assertIn(r.status_code, (200, 503))     # 503 khi thieu qrcode
        if r.status_code == 200:
            self.assertEqual(r.headers["content-type"], "image/png")
            self.assertEqual(r.content[:8], b"\x89PNG\r\n\x1a\n")

    # ---------------------------------------------------------------- sessions
    def test_tao_phong_va_doc_caption(self):
        r = client.post("/session/create", data={"topic": "hop",
                                                 "mode": "translate"})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        for k in ("sid", "link", "qr", "locked", "mode"):
            self.assertIn(k, j)
        self.assertFalse(j["locked"])
        sid = j["sid"]
        self.assertTrue(j["link"].endswith(f"/room/{sid}"))

        rooms.add_caption(sid, "hello", "xin chao", "Speaker 1",
                          t_start=1.0, t_end=2.0)
        c = client.get(f"/session/{sid}/captions?since=0").json()
        self.assertEqual(len(c["captions"]), 1)
        self.assertEqual(c["captions"][0]["vi"], "xin chao")
        self.assertEqual(c["mode"], "translate")

    def test_phong_pin_chan_dung_cach(self):
        sid = client.post("/session/create",
                          data={"topic": "mat", "pin": "2468"}).json()["sid"]
        self.assertEqual(client.get(f"/session/{sid}/captions").status_code, 403)
        self.assertEqual(client.get(f"/session/{sid}/captions?pin=sai").status_code, 403)
        ok = client.get(f"/session/{sid}/captions",
                        headers={"X-Room-Pin": "2468"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(client.get(f"/session/{sid}/captions?pin=2468").status_code, 200)
        self.assertEqual(client.delete(f"/session/{sid}").status_code, 403)
        self.assertEqual(client.delete(f"/session/{sid}",
                                       headers={"X-Room-Pin": "2468"}).status_code, 200)

    def test_phong_khong_ton_tai_tra_404(self):
        self.assertEqual(client.get("/session/khongco/captions").status_code, 404)
        self.assertEqual(client.get("/session/khongco/export").status_code, 404)
        self.assertEqual(client.post("/session/khongco/summary").status_code, 404)

    def test_context_giua_cuoc_hop(self):
        sid = client.post("/session/create", data={"topic": "t"}).json()["sid"]
        r = client.post(f"/session/{sid}/context",
                        json={"scenario": "tech", "keywords": "Whisper, VinAI",
                              "terms": "latency=độ trễ"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("saved") or "scenario" in r.json())
        self.assertEqual(server.LIVE_CONTEXT[sid]["scenario"], "tech")

    def test_export_txt_srt_vtt(self):
        sid = client.post("/session/create", data={"topic": "t"}).json()["sid"]
        rooms.add_caption(sid, "hello world", "xin chao the gioi",
                          t_start=10.0, t_end=12.0)
        rooms.add_caption(sid, "second line", "dong thu hai",
                          t_start=20.0, t_end=22.5)
        for fmt, needle in (("txt", "EN: hello world"), ("srt", "-->"),
                            ("vtt", "WEBVTT")):
            r = client.get(f"/session/{sid}/export?format={fmt}")
            self.assertEqual(r.status_code, 200, fmt)
            self.assertIn(needle, r.text)
        self.assertIn("xin chao the gioi",
                      client.get(f"/session/{sid}/export?format=txt&mode=vi").text)

    def test_tom_tat_offline(self):
        sid = client.post("/session/create", data={"topic": "t"}).json()["sid"]
        rooms.add_caption(sid, "We need to send the report.",
                          "Chúng ta cần gửi báo cáo.")
        r = client.post(f"/session/{sid}/summary")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertIn("summary", j)
        self.assertIn("actions", j)
        self.assertEqual(j["engine"], "offline-extractive")
        self.assertEqual(j["n_captions"], 1)

    def test_qr_png(self):
        sid = client.post("/session/create", data={"topic": "t"}).json()["sid"]
        r = client.get(f"/session/{sid}/qr.png")
        self.assertIn(r.status_code, (200, 503))     # 503 khi thieu qrcode
        if r.status_code == 200:
            self.assertEqual(r.headers["content-type"], "image/png")

    def test_summarize_endpoint(self):
        r = client.post("/summarize", json={"vi_text": "Chúng ta cần kiểm tra API."})
        self.assertEqual(r.status_code, 200)
        self.assertIn("summary", r.json())

    def test_health_co_thong_tin_nmt(self):
        j = client.get("/health").json()
        self.assertIn("nmt", j)
        self.assertIn("nmt_remote", j)

    def test_translate_endpoint_cho_may_khac_goi_vao(self):
        """Che do GPU tu xa: may yeu gui TEXT len day de dich (khong gui audio).

        Bom mot pipeline gia de khong phai tai model that.
        """
        import app.server as srv

        class FakeNMT:
            engine = "fake-gpu"

            def translate(self, text, accurate=False):
                return ("VI:" + text, 7.5)

        old = srv._pipe
        srv._pipe = type("P", (), {"nmt": FakeNMT()})()
        try:
            r = client.post("/translate", json={"text": "Hello world",
                                                "accurate": False})
            self.assertEqual(r.status_code, 200)
            j = r.json()
            self.assertEqual(j["vi"], "VI:Hello world")
            self.assertAlmostEqual(j["ms"], 7.5)
            self.assertEqual(j["engine"], "fake-gpu")
            # text rong -> khong goi model
            r2 = client.post("/translate", json={"text": "   "})
            self.assertEqual(r2.json()["vi"], "")
        finally:
            srv._pipe = old

    # LUU Y: KHONG test /translate_file hay /doctranslate o day.
    # Hai endpoint nay goi ensure_pipe() -> tai that Whisper + VinAI (1-2 phut, can mang).
    # Nhanh 503 chi xay ra khi tai model THAT BAI, khong the gia lap ma khong tai.


class TestServerWs(unittest.TestCase):
    def setUp(self):
        rooms.SESSIONS.clear()
        rooms._LISTENERS.clear()
        server.LIVE_CONTEXT.clear()

    def tearDown(self):
        rooms.SESSIONS.clear()
        rooms._LISTENERS.clear()

    def test_ws_room_nhan_snapshot_va_caption_realtime(self):
        sid = rooms.create_session("t")
        rooms.add_caption(sid, "cau mot", "cau mot vi")
        with client.websocket_connect(f"/ws/room/{sid}") as ws:
            snap = ws.receive_json()
            self.assertEqual(snap["kind"], "snapshot")
            self.assertEqual(len(snap["captions"]), 1)
            rooms.add_caption(sid, "cau hai", "cau hai vi")
            msg = ws.receive_json()
            self.assertEqual(msg["kind"], "caption")
            self.assertEqual(msg["en"], "cau hai")

    def test_ws_room_sai_pin_bi_tu_choi(self):
        sid = rooms.create_session("t", pin="9999")
        with client.websocket_connect(f"/ws/room/{sid}") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg["kind"], "status")
            self.assertEqual(msg["status"], "error")
            self.assertIn("PIN", msg["msg"])

    def test_ws_room_phong_khong_ton_tai(self):
        with client.websocket_connect("/ws/room/khongco") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg["status"], "error")

    def test_ws_stream_phong_khong_ton_tai_tu_choi_truoc_khi_tai_model(self):
        """Nhanh tu choi phai xay ra TRUOC ensure_pipe -> khong keo model ve."""
        with client.websocket_connect("/ws/stream?sid=khongco") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg["kind"], "status")
            self.assertEqual(msg["status"], "error")

    def test_ws_stream_sai_pin_tu_choi(self):
        sid = rooms.create_session("t", pin="1111")
        with client.websocket_connect(f"/ws/stream?sid={sid}&pin=sai") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg["status"], "error")
            self.assertIn("PIN", msg["msg"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

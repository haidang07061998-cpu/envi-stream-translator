"""Test che do GPU TU XA (RemoteNMT) — khong can model, khong can mang that.

Loi ich cua che do nay: may yeu chi chay ASR (nhe ~75MB) va gui TEXT len may GPU thue
de dich, thay vi phai giu model NMT 1.8GB. Test nay dung mot HTTP server gia de kiem
chung giao thuc, khong tai model nao.
"""
import json
import os
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nmt import RemoteNMT, build_nmt, remote_nmt_url   # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    received = []
    fail = False

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        _Handler.received.append(body)
        if _Handler.fail:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"loi")
            return
        vi = "VI:" + (body.get("text") or "")
        payload = json.dumps({"vi": vi, "ms": 12.5, "engine": "fake-gpu"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


class TestRemoteNMT(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.srv.server_address[1]
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()
        cls.url = f"http://127.0.0.1:{cls.port}"
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        _Handler.received.clear()
        _Handler.fail = False

    def test_dich_qua_mang_tra_ve_vi(self):
        n = RemoteNMT(self.url)
        vi, ms = n.translate("Hello world")
        self.assertEqual(vi, "VI:Hello world")
        self.assertAlmostEqual(ms, 12.5)
        self.assertEqual(_Handler.received[0]["text"], "Hello world")
        self.assertEqual(n.calls, 1)
        self.assertIn("remote", n.engine)

    def test_gui_nhieu_cau(self):
        n = RemoteNMT(self.url)
        outs, ms = n.translate(["a", "b"])
        self.assertEqual(outs, ["VI:a", "VI:b"])
        self.assertEqual(len(_Handler.received), 2)

    def test_text_rong_khong_goi_mang(self):
        n = RemoteNMT(self.url)
        vi, ms = n.translate("   ")
        self.assertEqual(vi, "")
        self.assertEqual(_Handler.received, [])

    def test_may_chu_loi_thi_khong_lam_vo_luong(self):
        """May GPU chet -> tra chuoi rong chu KHONG nem loi (mic van chay)."""
        _Handler.fail = True
        n = RemoteNMT(self.url, timeout=5)
        vi, ms = n.translate("Hello")
        self.assertEqual(vi, "")
        self.assertEqual(n.errors, 1)
        self.assertIsNotNone(n.last_error)

    def test_set_glossary_khong_loi(self):
        RemoteNMT(self.url).set_glossary({"a": "b"})     # phai im lang, khong nem


class TestBuildNmt(unittest.TestCase):
    """build_nmt() la diem vao duy nhat: co NMT_REMOTE_URL thi dung GPU tu xa."""

    def test_mac_dinh_khong_co_url(self):
        env = {k: v for k, v in os.environ.items() if k != "NMT_REMOTE_URL"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(remote_nmt_url(), "")

    def test_co_url_thi_tra_ve_remote(self):
        with mock.patch.dict(os.environ, {"NMT_REMOTE_URL": "http://gpu:8000/"},
                             clear=False):
            self.assertEqual(remote_nmt_url(), "http://gpu:8000")
            n = build_nmt("vinai/khong-can-tai", "en_XX", "vi_VN")
            self.assertIsInstance(n, RemoteNMT)
            self.assertEqual(n.engine, "remote:http://gpu:8000")


if __name__ == "__main__":
    unittest.main(verbosity=2)

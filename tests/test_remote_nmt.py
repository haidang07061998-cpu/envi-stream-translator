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
    health = {"loaded": True, "asr": "fake", "nmt": {"engine": "hf-cuda", "device": "cuda"}}

    def do_GET(self):
        if self.path.startswith("/health"):
            payload = json.dumps(_Handler.health).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

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

    def test_cache_tiet_kiem_request_len_gpu(self):
        """Cau lap lai khong duoc goi GPU lan 2 -> tiet kiem tien (tra theo giay)."""
        n = RemoteNMT(self.url)
        vi1, _ = n.translate("Thank you")
        vi2, _ = n.translate("Thank you")
        self.assertEqual(vi1, vi2)
        self.assertEqual(n.calls, 1, "chi duoc goi GPU 1 lan")
        self.assertEqual(n.cache_hits, 1)
        self.assertEqual(len(_Handler.received), 1)
        # accurate khac -> key khac -> goi lai (khong dung nham ban live)
        n.translate("Thank you", accurate=True)
        self.assertEqual(n.calls, 2)

    def test_cache_co_tran(self):
        n = RemoteNMT(self.url, cache_size=2)
        for s in ("a", "b", "c"):
            n.translate(s)
        self.assertLessEqual(len(n._cache), 2)


class TestBuildNmt(unittest.TestCase):
    """build_nmt() la diem vao duy nhat: co NMT_REMOTE_URL thi dung GPU tu xa."""

    def test_mac_dinh_khong_co_url(self):
        """Khong co env VA khong co gpu_url.txt -> rong (dich tai may).

        Phai tro _BASE vao thu muc tam, neu khong se doc nham gpu_url.txt that cua repo.
        """
        import src.config as cfg
        import tempfile
        env = {k: v for k, v in os.environ.items() if k != "NMT_REMOTE_URL"}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(cfg, "_BASE", d):
            self.assertEqual(remote_nmt_url(), "")

    def test_co_url_thi_tra_ve_remote(self):
        with mock.patch.dict(os.environ, {"NMT_REMOTE_URL": "http://gpu:8000/"},
                             clear=False):
            self.assertEqual(remote_nmt_url(), "http://gpu:8000")
            n = build_nmt("vinai/khong-can-tai", "en_XX", "vi_VN")
            self.assertIsInstance(n, RemoteNMT)
            self.assertEqual(n.engine, "remote:http://gpu:8000")


class TestGpuUrlConfig(unittest.TestCase):
    """Tich hop: URL may GPU doc tu bien moi truong HOAC file gpu_url.txt."""

    def test_doc_url_tu_file_gpu_url_txt(self):
        import src.config as cfg
        import tempfile
        env = {k: v for k, v in os.environ.items() if k != "NMT_REMOTE_URL"}
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, cfg.GPU_URL_FILE), "w", encoding="utf-8") as f:
                f.write("# ghi chu\nhttps://abc.trycloudflare.com/\n")
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(cfg, "_BASE", d):
                self.assertEqual(cfg.resolve_nmt_remote(),
                                 "https://abc.trycloudflare.com")
            # bien moi truong phai THANG file
            with mock.patch.dict(os.environ, {"NMT_REMOTE_URL": "https://env-url"},
                                 clear=False), mock.patch.object(cfg, "_BASE", d):
                self.assertEqual(cfg.resolve_nmt_remote(), "https://env-url")

    def test_luu_roi_doc_lai(self):
        import src.config as cfg
        import tempfile
        env = {k: v for k, v in os.environ.items() if k != "NMT_REMOTE_URL"}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(cfg, "_BASE", d):
            cfg.save_nmt_remote("https://xyz.trycloudflare.com/")
            self.assertEqual(cfg.resolve_nmt_remote(), "https://xyz.trycloudflare.com")
            cfg.save_nmt_remote("")            # tat GPU tu xa
            self.assertEqual(cfg.resolve_nmt_remote(), "")

    def test_khong_co_gi_thi_rong(self):
        import src.config as cfg
        import tempfile
        env = {k: v for k, v in os.environ.items() if k != "NMT_REMOTE_URL"}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(cfg, "_BASE", d):
            self.assertEqual(cfg.resolve_nmt_remote(), "")

    def test_chiu_duoc_bom_va_dong_rac(self):
        """LOI THAT: Notepad/PowerShell ghi BOM (\\ufeff) -> dong chu thich bi coi la URL.

        Da gap that: 'InvalidURL: Failed to parse: \\ufeff# Dia chi may GPU...'
        """
        import src.config as cfg
        import tempfile
        env = {k: v for k, v in os.environ.items() if k != "NMT_REMOTE_URL"}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(cfg, "_BASE", d):
            p = os.path.join(d, cfg.GPU_URL_FILE)
            with open(p, "w", encoding="utf-8-sig") as f:      # co BOM
                f.write("# ghi chu tieng Viet co dau\n")
                f.write("https://bom-test.trycloudflare.com/\n")
            self.assertEqual(cfg.resolve_nmt_remote(),
                             "https://bom-test.trycloudflare.com")
            # dong rac khong bat dau bang http -> phai bo qua, khong tra ve rac
            with open(p, "w", encoding="utf-8") as f:
                f.write("ghi chu lung tung\nhttps://sau-rac.trycloudflare.com\n")
            self.assertEqual(cfg.resolve_nmt_remote(),
                             "https://sau-rac.trycloudflare.com")


class TestCheckRemote(unittest.TestCase):
    """check_remote() cho UI biet dang chay GPU hay CPU."""

    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_phat_hien_dung_gpu(self):
        from src.config import check_remote
        _Handler.health = {"loaded": True, "asr": "large-v3-turbo",
                           "nmt": {"engine": "hf-cuda", "device": "cuda"}}
        info = check_remote(self.url, timeout=5)
        self.assertTrue(info["ok"])
        self.assertEqual(info["device"], "cuda")
        self.assertEqual(info["engine"], "hf-cuda")
        self.assertEqual(info["asr"], "large-v3-turbo")

    def test_canh_bao_khi_khong_co_gpu(self):
        from src.config import check_remote
        _Handler.health = {"loaded": True, "asr": "tiny.en",
                           "nmt": {"engine": "hf-cpu", "device": "cpu"}}
        info = check_remote(self.url, timeout=5)
        self.assertTrue(info["ok"])
        self.assertEqual(info["device"], "cpu")

    def test_url_chet_tra_ve_loi_chu_khong_nem(self):
        from src.config import check_remote
        info = check_remote("http://127.0.0.1:1", timeout=2)
        self.assertFalse(info["ok"])
        self.assertIsNotNone(info["error"])

    def test_chua_co_url(self):
        from src.config import check_remote
        info = check_remote("", timeout=2)
        self.assertFalse(info["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

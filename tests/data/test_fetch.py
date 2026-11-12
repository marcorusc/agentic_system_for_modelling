from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.data import fetch, ledger
from scripts.data.common import sha256_file

BODY = b"a,b\n1,2\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/page"):
            body, ctype = b"<!DOCTYPE html><html>no</html>", "text/html"
        elif self.path.startswith("/sneaky"):
            body, ctype = b"  \n<HTML><body>x", "text/plain"
        else:
            body, ctype = BODY, "text/csv"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class FetchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        sid = "data-20260101T000000Z-abcdef12"
        self.session = self.root / "runs" / "data-analyst" / sid
        for sub in ("scripts", "raw", "outputs", "proposals"):
            (self.session / sub).mkdir(parents=True)

    def lines(self):
        path = self.session / "sources.jsonl"
        if not path.exists():
            return []
        return [json.loads(x) for x in path.read_text().splitlines()]

    def dl(self, url=None, name="t.csv", **kw):
        return fetch.download(
            self.session, url=url or self.base + "/x", name=name,
            release="r1", root=self.root, **kw)

    def test_download_cached_and_ledgered(self):
        entry = self.dl()
        cache = self.root / "data-cache" / "sha256" / entry["sha256"]
        self.assertTrue(cache.is_file())
        self.assertEqual(cache.read_bytes(), BODY)
        lines = self.lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["kind"], "download")
        self.assertEqual(lines[0]["path"], str(cache))
        meta = json.loads((self.session / "raw" / "t.csv.source.json").read_text())
        self.assertEqual(meta["sha256"], entry["sha256"])
        self.assertEqual(meta["content_type"], "text/csv")
        self.assertEqual(meta["release"], "r1")
        self.assertEqual(list((self.root / "data-cache").glob("tmp-*")), [])

    def test_second_download_reuses_cache(self):
        first = self.dl(name="a.csv")
        cache = self.root / "data-cache" / "sha256" / first["sha256"]
        mtime = cache.stat().st_mtime_ns
        second = self.dl(name="b.csv")
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(cache.stat().st_mtime_ns, mtime)
        self.assertEqual(len(list((self.root / "data-cache" / "sha256").iterdir())), 1)
        self.assertEqual(len(self.lines()), 2)

    def test_download_function_with_query_string(self):
        entry = self.dl(url=self.base + "/x?a=1&b=2")
        self.assertEqual(entry["uri"], self.base + "/x?a=1&b=2")
        self.assertEqual(sha256_file(Path(entry["path"])), entry["sha256"])

    def test_html_rejected_when_tabular_expected(self):
        for path in ("/page", "/sneaky"):
            with self.assertRaisesRegex(ValueError, "received HTML, expected tabular"):
                self.dl(url=self.base + path, expect="tabular")
        self.assertEqual(self.lines(), [])
        self.assertFalse((self.session / "raw" / "t.csv.source.json").exists())
        self.assertEqual(list((self.root / "data-cache").glob("tmp-*")), [])

    def test_no_overwrite_and_bad_name(self):
        self.dl()
        with self.assertRaises(ValueError):
            self.dl()
        for bad in ("../x", "a/b", "..", ""):
            with self.assertRaises(ValueError):
                self.dl(name=bad)

    def test_max_bytes(self):
        with self.assertRaises(ValueError):
            self.dl(max_bytes=3)
        self.assertEqual(list((self.root / "data-cache").glob("tmp-*")), [])

    def test_record_api_writes_raw_and_ledger(self):
        entry = ledger.record_api(
            self.session, url="https://example.org/api", params={"b": "2", "a": "1"},
            response='{"ok": 1}', release="v9", name="api.json")
        self.assertEqual((self.session / "raw" / "api.json").read_text(), '{"ok": 1}')
        self.assertEqual(entry["uri"], "https://example.org/api?a=1&b=2")
        self.assertEqual(self.lines()[0]["kind"], "api")
        with self.assertRaises(ValueError):
            ledger.record_api(self.session, url="u", params={}, response=b"x",
                              release="v9", name="api.json")

    def test_input_outside_inputs_rejected(self):
        (self.root / "inputs").mkdir()
        good = self.root / "inputs" / "d.csv"
        good.write_bytes(BODY)
        entry = ledger.record_input(self.session, good, self.root)
        self.assertEqual(entry["kind"], "input")
        self.assertEqual(entry["sha256"], sha256_file(good))
        self.assertEqual(entry["release"], "researcher-supplied")
        bad = self.root / "other.csv"
        bad.write_bytes(BODY)
        with self.assertRaises(ValueError):
            ledger.record_input(self.session, bad, self.root)
        self.assertEqual(len(self.lines()), 1)

    def test_ledger_rejects_missing_release(self):
        entry = {"kind": "api", "uri": "u", "release": "", "retrieved_at": "t",
                 "sha256": "0" * 64, "terms": "", "path": "p"}
        with self.assertRaises(ValueError):
            ledger.append(self.session, entry)
        with self.assertRaises(ValueError):
            ledger.validate_entry({**entry, "release": "r", "sha256": "xyz"})
        with self.assertRaises(ValueError):
            ledger.validate_entry({**entry, "release": "r", "kind": "bogus"})
        self.assertEqual(self.lines(), [])


if __name__ == "__main__":
    unittest.main()

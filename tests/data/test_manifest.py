from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from scripts.data import fetch, ledger, manifest, session
from scripts.data.common import session_dir

CSV = b"gene,score\nA,1\n"


class _CsvHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Length", str(len(CSV)))
        self.end_headers()
        self.wfile.write(CSV)

    def log_message(self, *args):
        pass


class ManifestTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "DECISIONS.md").write_text("original\n", encoding="utf-8")
        (self.root / "setup").mkdir()
        (self.root / "setup" / "data-requirements.lock").write_text("pkg==1\n", encoding="utf-8")
        self.sid, _ = session.new_session(self.root, "test", None)
        self.dir = session_dir(self.root, self.sid)
        (self.dir / "scripts" / "01_de.py").write_text("print(1)\n", encoding="utf-8")
        (self.dir / "outputs" / "de.csv").write_text(
            "gene,log2FoldChange,padj\nA,1.5,0.01\nB,-2,0.2\n", encoding="utf-8"
        )
        self.write_json(
            "outputs/index.json",
            [{"path": "outputs/de.csv", "description": "DE",
              "units": {"log2FoldChange": "log2 ratio", "padj": "dimensionless"},
              "identifiers": "HGNC symbol"}],
        )
        (self.dir / "proposals" / "P1_seed_genes.csv").write_text("gene\nA\n", encoding="utf-8")
        self.write_json(
            "proposals/index.json",
            [{"id": "P1", "target_layer": "neko", "kind": "seed_genes",
              "path": "proposals/P1_seed_genes.csv", "method": "padj filter",
              "thresholds": {"padj": 0.05}}],
        )

    def write_json(self, rel, data):
        (self.dir / rel).write_text(json.dumps(data), encoding="utf-8")

    def build(self, skills=("pydeseq2",)):
        return manifest.build(self.root, self.sid, list(skills))

    def load(self):
        return json.loads((self.dir / "manifest.json").read_text(encoding="utf-8"))

    def save(self, data):
        (self.dir / "manifest.json").write_text(json.dumps(data), encoding="utf-8")

    def errors(self):
        return manifest.verify(self.root, self.sid)

    def test_round_trip_passes(self):
        data = self.build()
        self.assertEqual(self.errors(), [])
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["specialist"], "data_analyst")
        self.assertEqual(data["stage"], "data")
        self.assertEqual(data["session_id"], self.sid)
        self.assertIsNone(data["derived_from_session_id"])
        self.assertEqual(data["scripts"][0]["path"], "scripts/01_de.py")
        self.assertEqual(data["outputs"][0]["path"], "outputs/de.csv")
        self.assertEqual(data["vendored_skills_used"], ["pydeseq2"])
        self.assertEqual(len(data["environment"]["lock_sha256"]), 64)

    def test_missing_manifest_rejected(self):
        self.assertTrue(any("manifest.json" in e for e in self.errors()))

    def test_changed_output_hash_rejected(self):
        self.build()
        (self.dir / "outputs" / "de.csv").write_text("gene,padj\nA,0.5\n", encoding="utf-8")
        self.assertTrue(any("hash" in e and "outputs/de.csv" in e for e in self.errors()))

    def test_unlisted_output_rejected(self):
        self.build()
        (self.dir / "outputs" / "extra.txt").write_text("x", encoding="utf-8")
        self.assertTrue(any("extra.txt" in e for e in self.errors()))

    def test_unlisted_script_rejected(self):
        self.build()
        (self.dir / "scripts" / "02.py").write_text("x=1\n", encoding="utf-8")
        self.assertTrue(any("02.py" in e for e in self.errors()))

    def test_symlinked_output_rejected(self):
        self.build()
        target = self.root / "secret.csv"
        target.write_text("gene,log2FoldChange,padj\nA,1.5,0.01\nB,-2,0.2\n", encoding="utf-8")
        out = self.dir / "outputs" / "de.csv"
        out.unlink()
        out.symlink_to(target)
        self.assertTrue(any("symlink" in e for e in self.errors()))

    def test_numeric_column_without_unit_rejected(self):
        self.write_json(
            "outputs/index.json",
            [{"path": "outputs/de.csv", "description": "DE",
              "units": {"log2FoldChange": "log2 ratio"}, "identifiers": "HGNC symbol"}],
        )
        self.build()
        errs = self.errors()
        self.assertTrue(any("padj" in e for e in errs), errs)

    def test_dimensionless_string_accepts_numeric_columns(self):
        idx = json.loads((self.dir / "outputs/index.json").read_text())
        idx[0]["units"] = "dimensionless"
        self.write_json("outputs/index.json", idx)
        self.build()
        self.assertEqual(self.errors(), [])

    def test_non_tabular_needs_units(self):
        (self.dir / "outputs" / "plot.txt").write_text("x", encoding="utf-8")
        idx = json.loads((self.dir / "outputs/index.json").read_text())
        idx.append({"path": "outputs/plot.txt", "description": "p", "identifiers": "none"})
        self.write_json("outputs/index.json", idx)
        self.build()
        self.assertTrue(any("units" in e and "plot.txt" in e for e in self.errors()))
        idx[1]["units"] = "none"
        self.write_json("outputs/index.json", idx)
        self.build()
        self.assertEqual(self.errors(), [])

    def test_empty_identifiers_rejected(self):
        idx = json.loads((self.dir / "outputs/index.json").read_text())
        idx[0]["identifiers"] = ""
        self.write_json("outputs/index.json", idx)
        self.build()
        self.assertTrue(any("identifiers" in e for e in self.errors()))

    def test_unknown_skill_rejected(self):
        self.build(skills=("not-a-skill",))
        self.assertTrue(any("not-a-skill" in e for e in self.errors()))

    def test_bad_proposal_kind_rejected(self):
        idx = json.loads((self.dir / "proposals/index.json").read_text())
        idx[0]["kind"] = "bogus"
        self.write_json("proposals/index.json", idx)
        self.build()
        self.assertTrue(any("kind" in e for e in self.errors()))

    def test_bad_and_duplicate_proposal_ids_rejected(self):
        idx = json.loads((self.dir / "proposals/index.json").read_text())
        (self.dir / "proposals" / "b.csv").write_text("g\nB\n", encoding="utf-8")
        idx.append(dict(idx[0], id="P1", path="proposals/b.csv"))
        idx.append(dict(idx[0], id="Q2", path="proposals/b.csv"))
        self.write_json("proposals/index.json", idx)
        self.build()
        errs = self.errors()
        self.assertTrue(any("duplicate" in e for e in errs), errs)
        self.assertTrue(any("Q2" in e for e in errs), errs)

    def test_bad_source_rejected(self):
        (self.dir / "sources.jsonl").write_text(
            json.dumps({"kind": "api", "uri": "u"}) + "\n", encoding="utf-8"
        )
        self.build()
        self.assertTrue(any("source" in e for e in self.errors()))

    def serve(self) -> str:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _CsvHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}/x.csv"

    def test_in_place_edit_of_downloaded_source_detected(self):
        entry = fetch.download(self.dir, url=self.serve(), name="x.csv", release="r1", root=self.root)
        self.build()
        self.assertEqual(self.errors(), [])
        cache = self.root / entry["path"]
        cache.chmod(0o644)
        cache.write_bytes(b"gene,score\nA,999\n")
        errs = self.errors()
        self.assertTrue(any("source 0" in e and "hash mismatch" in e for e in errs), errs)

    def test_in_place_edit_of_api_response_detected(self):
        entry = ledger.record_api(self.dir, url="https://example.org/api", params={},
                                  response='{"ok": 1}', release="v1", name="api.json")
        self.build()
        self.assertEqual(self.errors(), [])
        (self.root / entry["path"]).write_text('{"ok": 2}', encoding="utf-8")
        errs = self.errors()
        self.assertTrue(any("source 0" in e and "hash mismatch" in e for e in errs), errs)

    def test_missing_or_escaping_source_path_rejected(self):
        entry = ledger.record_api(self.dir, url="https://example.org/api", params={},
                                  response="x", release="v1", name="api.json")
        for bad in (str(self.root / entry["path"]), "../outside", "DECISIONS.md",
                    entry["path"] + ".missing"):
            with self.subTest(path=bad):
                (self.dir / "sources.jsonl").write_text(
                    json.dumps({**entry, "path": bad}) + "\n", encoding="utf-8")
                self.build()
                errs = self.errors()
                self.assertTrue(any("source 0" in e for e in errs), errs)

    def test_manifest_sources_must_equal_ledger(self):
        ledger.record_api(self.dir, url="https://example.org/api", params={},
                          response="x", release="v1", name="api.json")
        self.build()
        self.assertEqual(self.errors(), [])
        ledger.record_api(self.dir, url="https://example.org/api2", params={},
                          response="y", release="v1", name="api2.json")
        errs = self.errors()
        self.assertTrue(any("sources.jsonl" in e for e in errs), errs)
        self.build()
        self.assertEqual(self.errors(), [])
        data = self.load()
        data["sources"] = data["sources"][:1]
        self.save(data)
        errs = self.errors()
        self.assertTrue(any("sources.jsonl" in e for e in errs), errs)

    def test_identity_mismatch_rejected(self):
        self.build()
        data = self.load()
        data["session_id"] = "data-20200101T000000Z-deadbeef"
        self.save(data)
        self.assertTrue(any("session_id" in e for e in self.errors()))

    def test_status_always_proposed(self):
        idx = json.loads((self.dir / "proposals/index.json").read_text())
        idx[0]["status"] = "approved"
        self.write_json("proposals/index.json", idx)
        data = self.build()
        self.assertEqual(data["proposals"][0]["status"], "proposed")
        data["proposals"][0]["status"] = "approved"
        self.save(data)
        self.assertTrue(any("status" in e for e in self.errors()))

    def test_absent_indexes_mean_empty(self):
        (self.dir / "outputs" / "index.json").unlink()
        (self.dir / "outputs" / "de.csv").unlink()
        (self.dir / "proposals" / "index.json").unlink()
        (self.dir / "proposals" / "P1_seed_genes.csv").unlink()
        data = self.build()
        self.assertEqual((data["outputs"], data["proposals"]), ([], []))
        self.assertEqual(self.errors(), [])

    def test_cli(self):
        out = mock.patch("sys.stdout", new_callable=io.StringIO)
        err = mock.patch("sys.stderr", new_callable=io.StringIO)
        out.start(); err.start()
        self.addCleanup(out.stop); self.addCleanup(err.stop)
        self.assertEqual(manifest.main(["build", "--session", self.sid, "--skills", "pydeseq2"]), 0)
        self.assertEqual(manifest.main(["verify", "--session", self.sid]), 0)
        (self.dir / "outputs" / "x.txt").write_text("x", encoding="utf-8")
        self.assertEqual(manifest.main(["verify", "--session", self.sid]), 1)


if __name__ == "__main__":
    unittest.main()

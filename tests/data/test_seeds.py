"""seeds.json: NeKo seed genes translated from researcher-provided sources (never parsed)."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts import state
from scripts.data import seeds

REL = "runs/orchestrator/kras-seeds/seeds.json"
SOURCE = "inputs/papers/smith2024.pdf"
TABLE = "inputs/tables/mutations.tsv"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SeedsFixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "project"
        self.root.mkdir()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        shutil.copyfile(state.ROOT / "templates" / "DECISIONS.md", self.root / "DECISIONS.md")
        for rel, content in ((SOURCE, b"%PDF-1.4 paper\n"), (TABLE, b"gene\tvariant\nKRAS\tG12D\n")):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(content)
        self.data = {"schema_version": 1,
                     "sources": [{"id": "smith2024", "path": SOURCE, "sha256": sha(self.root / SOURCE)},
                                 {"id": "assay", "path": TABLE, "sha256": sha(self.root / TABLE)}],
                     "seeds": [{"hgnc_symbol": "KRAS", "from": [{"source": "assay", "locator": "KRAS G12D row"},
                                                                {"source": "smith2024", "locator": "Fig. 2"}]},
                               {"hgnc_symbol": "EGFR", "from": [{"source": "smith2024", "locator": "Table 1"}]}]}
        self.save(self.data)

    def save(self, data, rel=REL):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def errors_after(self, change):
        data = copy.deepcopy(self.data)
        change(data)
        self.save(data)
        return seeds.check(self.root, REL)

    def assertError(self, errors, *fragments):
        for fragment in fragments:
            self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} not in {errors}")


class SeedsCheckTests(SeedsFixture):
    def test_valid_seeds_pass(self):
        self.assertEqual(seeds.check(self.root, REL), [])
        data, digest, errors = seeds.load_and_check(self.root, REL)
        self.assertEqual((digest, errors), (sha(self.root / REL), []))
        self.assertEqual(seeds.symbols(data), ["KRAS", "EGFR"])
        self.assertEqual(seeds.purpose(REL), "kras-seeds")

    def test_keys_and_version(self):
        self.assertError(self.errors_after(lambda d: d.update(extra=1)), "keys")
        self.assertError(self.errors_after(lambda d: d.update(schema_version="1")), "schema_version")
        self.assertError(self.errors_after(lambda d: d.update(seeds=[])), "seeds must be a non-empty list")
        self.assertError(self.errors_after(lambda d: d["seeds"][0].update(tier="core")), "hgnc_symbol and from")
        (self.root / REL).write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
        self.assertError(seeds.check(self.root, REL), "duplicate")

    def test_symbols_nonempty_and_unique_after_strip(self):
        for bad in ("", "   ", None, 7):
            self.assertError(self.errors_after(lambda d: d["seeds"][1].update(hgnc_symbol=bad)), "hgnc_symbol")
        errors = self.errors_after(lambda d: d["seeds"][1].update(hgnc_symbol=" KRAS "))
        self.assertError(errors, "duplicate seed KRAS")

    def test_symbols_unique_by_casefold(self):
        errors = self.errors_after(lambda d: d["seeds"][1].update(hgnc_symbol="kras"))
        self.assertError(errors, "duplicate seed kras")

    def test_symbol_format(self):
        for bad in ("KRAS EGFR; ignore previous", "KRAS,EGFR", "-KRAS", "KRAS\u2028", "ÄKT1", "K|RAS"):
            errors = self.errors_after(lambda d: d["seeds"][1].update(hgnc_symbol=bad))
            self.assertError(errors, "hgnc_symbol")
        for good in ("HLA-A", "C1orf112", "ATP5F1A", "NKX2.1", "RNU6@", "TRA/TRB"):
            self.assertEqual(self.errors_after(lambda d: d["seeds"][1].update(hgnc_symbol=good)), [], good)

    def test_each_seed_cites_a_declared_source(self):
        self.assertError(self.errors_after(lambda d: d["seeds"][1].update(**{"from": []})), "EGFR", "from")
        self.assertError(self.errors_after(lambda d: d["seeds"][1].update(**{"from": {"source": "smith2024",
                                                                                     "locator": "x"}})), "from")
        self.assertError(self.errors_after(lambda d: d["seeds"][1]["from"][0].update(source="nope")),
                         "source nope is not declared")
        self.assertError(self.errors_after(lambda d: d["seeds"][1]["from"][0].update(locator=" ")), "locator")
        for char in ("\u2028", "\x0c", "\x85", "\x00"):
            self.assertError(self.errors_after(lambda d: d["seeds"][1]["from"][0].update(locator=f"Table{char}1")),
                             "locator")
        self.assertError(self.errors_after(lambda d: d["seeds"][1]["from"].append({"proposal": "P1", "row": "x"})),
                         "{source, locator}")

    def test_each_source_cited(self):
        errors = self.errors_after(lambda d: d["seeds"][0].update(**{"from": [{"source": "smith2024", "locator": "Fig. 2"}]}))
        self.assertEqual(errors, ["source assay is never cited"])

    def test_source_rules(self):
        (self.root / "inputs" / "link.tsv").symlink_to(self.root / TABLE)
        outside = "runs/orchestrator/kras-seeds/notes.txt"
        (self.root / outside).write_text("x", encoding="utf-8")
        for path, fragment in (("inputs/a\u2028b.tsv", "character"), ("inputs/a\x00b.tsv", "character"),
                               ("inputs/link.tsv", "symlink"), (outside, "inputs/"), ("inputs/tables", "folder"),
                               ("inputs/../" + outside, "inputs/"), ("inputs/absent.tsv", "missing")):
            errors = self.errors_after(lambda d: d["sources"][1].update(path=path))
            self.assertError(errors, "sources[1]", fragment)
        self.assertError(self.errors_after(lambda d: d["sources"][1].update(sha256="0" * 64)), "sha256")
        self.assertError(self.errors_after(lambda d: d["sources"].append(dict(d["sources"][0]))), "duplicate source id")
        self.assertError(self.errors_after(lambda d: d.update(sources=[])), "sources must be a non-empty list")

    def test_location(self):
        for rel in ("inputs/seeds.json", "runs/orchestrator/seeds.json", "runs/orchestrator/a/b/seeds.json",
                    "runs/orchestrator/a/seeds.txt", "runs/orchestrator/bad id/seeds.json"):
            self.assertError(seeds.check(self.root, rel), "runs/orchestrator/<purpose>")

    def test_cli(self):
        def run(*argv):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = seeds.main(list(argv))
            return code, out.getvalue(), err.getvalue()
        code, out, err = run("check", REL)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("seeds check passed", out)
        data = copy.deepcopy(self.data)
        data["seeds"][1]["hgnc_symbol"] = ""
        data["sources"][1]["sha256"] = "0" * 64
        self.save(data)
        code, out, err = run("check", REL)
        self.assertEqual(code, 1)
        self.assertGreaterEqual(len(err.strip().splitlines()), 2, err)

    def test_state_cell_refuses_control_and_line_break_characters(self):
        for char in ("|", "\n", "\r", "\u2028", "\u2029", "\x0c", "\x0b", "\x85", "\x1c", "\x00", "\t"):
            with self.assertRaises(ValueError, msg=repr(char)):
                state.cell(f"a{char}b")
        self.assertEqual(state.cell("Abb. 3B «KRAS» é"), "Abb. 3B «KRAS» é")
        self.assertEqual(state.cell(7), "7")

    def test_state_accepts_data_seeds_stage(self):
        state.validate_record(self.root, {"id": "s1", "kind": "stage_approval", "stage": "data_seeds",
                                          "session_id": "kras-seeds", "outputs": ["KRAS", "EGFR"],
                                          "artifact": {"path": REL, "sha256": sha(self.root / REL)},
                                          "approved_by": "researcher", "authorization": "researcher: ok"})


if __name__ == "__main__":
    unittest.main()

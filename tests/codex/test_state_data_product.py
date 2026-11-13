import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import state
from scripts.data import ledger

SESSION = "data-20260101T000000Z-abcdef12"
OTHER = "data-20260101T000000Z-0000beef"
REPO = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class DataProductTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in ("DATA_DICTIONARY.md", "DECISIONS.md"):
            shutil.copyfile(state.ROOT / "templates" / name, self.root / name)
        self.base = f"runs/data-analyst/{SESSION}"
        folder = self.root / self.base
        (folder / "outputs").mkdir(parents=True)
        (folder / "proposals").mkdir()
        self.file = folder / "outputs" / "table.tsv"
        self.file.write_bytes(b"a\tb\n1\t2\n")
        self.sha = sha(self.file)
        for pid in ("P1", "P2"):
            (folder / f"proposals/{pid}_seed_genes.csv").write_text(f"gene\n{pid}\n")
        (folder / "proposals/index.json").write_text(json.dumps([
            {"id": pid, "kind": "seed_genes", "target_layer": "neko", "path": f"proposals/{pid}_seed_genes.csv"}
            for pid in ("P1", "P2")]))
        self.unlisted = folder / "outputs" / "unlisted.tsv"
        self.unlisted.write_text("x\n")
        artifacts = [{"path": f"{self.base}/{rel}", "sha256": sha(folder / rel)}
                     for rel in ("outputs/table.tsv", "proposals/index.json",
                                 "proposals/P1_seed_genes.csv", "proposals/P2_seed_genes.csv")]
        self.handoff = folder / "handoff.json"
        self.handoff.write_text(json.dumps({"schema_version": 1, "stage": "data", "session_id": SESSION,
                                            "artifacts": artifacts}, indent=2))
        other = self.root / f"runs/data-analyst/{OTHER}"
        other.mkdir(parents=True)
        (other / "handoff.json").write_text(json.dumps({"session_id": OTHER, "artifacts": []}))
        self.approval = {"id": "dec-data-1", "kind": "stage_approval", "stage": "data", "session_id": SESSION,
                         "approved_by": "researcher", "authorization": "researcher: approve P1 and the table",
                         "outputs": ["P1"], "artifact": {"path": f"{self.base}/handoff.json", "sha256": sha(self.handoff)}}
        state.update(self.root, "record", self.approval)
        self.item = {"name": "expr_table", "type": "table", "meaning": "expression", "unit": "TPM",
                     "identifiers": "HGNC", "source_session": SESSION, "path": f"{self.base}/outputs/table.tsv",
                     "sha256": self.sha, "release": "v1", "decision_id": "dec-data-1", "notes": "ok"}

    def add_raw_record(self, record):
        # Bypasses state.py record validation on purpose: only data-product is under test.
        path = self.root / "DECISIONS.md"
        path.write_text(path.read_text().rstrip() + "\n\n<!-- governance-record -->\n```json\n"
                        + json.dumps(record) + "\n```\n")

    def refused(self, pattern, **changes):
        with self.assertRaisesRegex(ValueError, pattern):
            state.update(self.root, "data-product", {**self.item, **changes})
        self.assertEqual(self.rows(), [])

    def rows(self):
        return state.table((self.root / "DATA_DICTIONARY.md").read_text(), state.DATA_DICTIONARY)[3]

    def test_data_product_row_added(self):
        state.update(self.root, "data-product", self.item)
        row = self.rows()[0]
        self.assertEqual(row["Name"], "expr_table")
        self.assertEqual(row["Version"], "v1")
        self.assertIn(f"{SESSION}", row["Source"])
        self.assertIn(self.sha[:12], row["Source"])
        self.assertEqual(row["Notes"], "identifiers: HGNC; decision dec-data-1; ok")

    def test_data_product_duplicate_rejected(self):
        state.update(self.root, "data-product", self.item)
        with self.assertRaises(ValueError):
            state.update(self.root, "data-product", self.item)

    def test_data_product_hash_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            state.update(self.root, "data-product", {**self.item, "sha256": "0" * 64})
        with self.assertRaises(ValueError):
            state.update(self.root, "data-product", {**self.item, "path": "runs/missing.tsv"})
        with self.assertRaises(ValueError):
            state.update(self.root, "data-product", {**self.item, "source_session": "bogus"})
        self.assertEqual(self.rows(), [])

    def test_data_product_unknown_decision_rejected(self):
        with self.assertRaises(ValueError):
            state.update(self.root, "data-product", {**self.item, "decision_id": "nope"})
        self.assertEqual(self.rows(), [])

    def proposal(self, pid):
        rel = f"{self.base}/proposals/{pid}_seed_genes.csv"
        return {"name": f"seed_{pid}", "path": rel, "sha256": sha(self.root / rel)}

    def test_approved_proposal_accepted(self):
        state.update(self.root, "data-product", {**self.item, **self.proposal("P1")})
        self.assertEqual([r["Name"] for r in self.rows()], ["seed_P1"])

    def test_stage_review_record_rejected(self):
        self.add_raw_record({**self.approval, "id": "rev-1", "kind": "stage_review"})
        self.refused("must be a stage_approval", decision_id="rev-1")

    def test_other_stage_approval_rejected(self):
        self.add_raw_record({**self.approval, "id": "topo-1", "stage": "topology"})
        self.refused("stage data", decision_id="topo-1")

    def test_approval_for_other_session_rejected(self):
        other = f"runs/data-analyst/{OTHER}/handoff.json"
        self.add_raw_record({**self.approval, "id": "other-1", "session_id": OTHER,
                             "artifact": {"path": other, "sha256": sha(self.root / other)}})
        self.refused("approves session", decision_id="other-1")

    def test_approval_artifact_must_be_session_handoff(self):
        index = f"{self.base}/proposals/index.json"
        self.add_raw_record({**self.approval, "id": "idx-1",
                             "artifact": {"path": index, "sha256": sha(self.root / index)}})
        self.refused("handoff.json", decision_id="idx-1")
        other = f"runs/data-analyst/{OTHER}/handoff.json"
        self.add_raw_record({**self.approval, "id": "other-art",
                             "artifact": {"path": other, "sha256": sha(self.root / other)}})
        self.refused("handoff.json", decision_id="other-art")

    def test_handoff_changed_since_approval_rejected(self):
        self.handoff.write_text(self.handoff.read_text() + "\n")
        self.refused("changed since approval")

    def test_product_not_in_handoff_rejected(self):
        self.refused("not an artifact of the approved handoff",
                     path=f"{self.base}/outputs/unlisted.tsv", sha256=sha(self.unlisted))

    def test_product_changed_since_handoff_rejected(self):
        self.file.write_bytes(b"a\tb\n9\t9\n")
        self.refused("not an artifact of the approved handoff", sha256=sha(self.file))

    def test_unapproved_proposal_rejected(self):
        self.refused("proposal P2 is not in the approved outputs", **self.proposal("P2"))

    def test_proposals_index_changed_rejected(self):
        index = self.root / self.base / "proposals/index.json"
        data = json.loads(index.read_text())
        data[0]["path"], data[1]["path"] = data[1]["path"], data[0]["path"]
        index.write_text(json.dumps(data))
        self.refused("proposals/index.json", **self.proposal("P2"))

    def test_cli_runs_as_script_from_repo_root(self):
        product = self.root / "product.json"
        product.write_text(json.dumps(self.item))
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        proc = subprocess.run([sys.executable, "scripts/state.py", "data-product", "--input", str(product),
                               "--root", str(self.root)], cwd=REPO, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["path"], "DATA_DICTIONARY.md")
        self.assertEqual([r["Name"] for r in self.rows()], ["expr_table"])

    def _entry(self, terms):
        return {"kind": "api", "uri": "u", "release": "r", "retrieved_at": "t", "sha256": "0" * 64, "terms": terms, "path": "p"}

    def test_terms_free_text_rejected(self):
        for bad in ("CC-BY 4.0", "quoted: ", "quoted:x"):
            with self.assertRaises(ValueError):
                ledger.validate_entry(self._entry(bad))

    def test_terms_quoted_accepted(self):
        for ok in ("", "unverified", "quoted: CC-BY 4.0"):
            ledger.validate_entry(self._entry(ok))


if __name__ == "__main__":
    unittest.main()

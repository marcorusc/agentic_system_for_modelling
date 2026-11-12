import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import state
from scripts.data import ledger

SESSION = "data-20260101T000000Z-abcdef12"


class DataProductTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in ("DATA_DICTIONARY.md", "DECISIONS.md"):
            shutil.copyfile(state.ROOT / "templates" / name, self.root / name)
        folder = self.root / "runs/data-analyst" / SESSION
        folder.mkdir(parents=True)
        self.file = folder / "table.tsv"
        self.file.write_bytes(b"a\tb\n1\t2\n")
        self.sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        # A decision record id is the governance-record "id" in DECISIONS.md.
        text = (self.root / "DECISIONS.md").read_text()
        record = {"id": "dec-data-1", "kind": "standalone_approval"}
        (self.root / "DECISIONS.md").write_text(text.rstrip() + "\n\n<!-- governance-record -->\n```json\n" + json.dumps(record) + "\n```\n")
        self.item = {"name": "expr_table", "type": "table", "meaning": "expression", "unit": "TPM",
                     "identifiers": "HGNC", "source_session": SESSION, "path": str(self.file.relative_to(self.root)),
                     "sha256": self.sha, "release": "v1", "decision_id": "dec-data-1", "notes": "ok"}

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

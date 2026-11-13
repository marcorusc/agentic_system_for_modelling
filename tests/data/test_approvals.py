import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import state
from scripts.data import approvals

SESSION = "data-20260101T000000Z-abcdef12"
OTHER = "data-20260101T000000Z-0000beef"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copyfile(state.ROOT / "templates" / "DECISIONS.md", self.root / "DECISIONS.md")
        self.base = f"runs/data-analyst/{SESSION}"
        folder = self.root / self.base
        (folder / "proposals").mkdir(parents=True)
        for pid in ("P1", "P2"):
            (folder / f"proposals/{pid}_seed_genes.csv").write_text(f"hgnc_symbol,tier,evidence\n{pid},core,e\n")
        (folder / "proposals/index.json").write_text(json.dumps([
            {"id": pid, "kind": "seed_genes", "target_layer": "neko", "path": f"proposals/{pid}_seed_genes.csv"}
            for pid in ("P1", "P2")]))
        self.write_handoff(["proposals/index.json", "proposals/P1_seed_genes.csv", "proposals/P2_seed_genes.csv"])
        self.approval = self.add({"id": "dec-1", "kind": "stage_approval", "stage": "data", "session_id": SESSION,
                                  "outputs": ["P1"], "artifact": self.ref()})

    def ref(self):
        return {"path": f"{self.base}/handoff.json", "sha256": sha(self.root / self.base / "handoff.json")}

    def write_handoff(self, rels):
        folder = self.root / self.base
        arts = [{"path": f"{self.base}/{r}", "sha256": sha(folder / r)} for r in rels]
        (folder / "handoff.json").write_text(json.dumps({"session_id": SESSION, "artifacts": arts}))

    def add(self, record):
        record = {"approved_by": "researcher", "authorization": "researcher: ok", **record}
        state.update(self.root, "record", record)
        return record

    def test_data_approval_ok(self):
        rec = approvals.require_data_approval(self.root, "dec-1", SESSION)
        self.assertEqual(rec["id"], "dec-1")
        self.assertEqual(approvals.load_record(self.root, "dec-1")["id"], "dec-1")
        with self.assertRaisesRegex(ValueError, "not found"):
            approvals.load_record(self.root, "nope")
        got = approvals.require_proposal_approved(self.root, rec, SESSION, "P1")
        self.assertEqual(got["id"], "P1")
        self.assertEqual(got["path"], f"{self.base}/proposals/P1_seed_genes.csv")
        self.assertEqual(got["sha256"], sha(self.root / got["path"]))

    def test_stage_review_refused(self):
        folder = self.root / "reviews"
        folder.mkdir()
        (folder / "r.md").write_text("r")
        ref = {"path": "reviews/r.md", "sha256": sha(folder / "r.md")}
        self.add({"id": "rev-1", "kind": "stage_review", "stage": "data", "session_id": SESSION,
                  "outcome": "approved", "scientific-reviewer": ref, "reproducibility-auditor": ref,
                  "artifact": self.ref()})
        with self.assertRaisesRegex(ValueError, "must be a stage_approval"):
            approvals.require_data_approval(self.root, "rev-1", SESSION)

    def test_other_stage_refused(self):
        self.add({"id": "dec-top", "kind": "stage_approval", "stage": "topology", "session_id": SESSION,
                  "outputs": ["A"], "artifact": self.ref()})
        with self.assertRaisesRegex(ValueError, "must approve stage data"):
            approvals.require_data_approval(self.root, "dec-top", SESSION)

    def test_wrong_session_and_changed_handoff_refused(self):
        with self.assertRaisesRegex(ValueError, "approves session"):
            approvals.require_data_approval(self.root, "dec-1", OTHER)
        handoff = self.root / self.base / "handoff.json"
        handoff.write_text(handoff.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "changed since approval"):
            approvals.require_data_approval(self.root, "dec-1", SESSION)

    def test_proposal_not_in_outputs_refused(self):
        rec = approvals.require_data_approval(self.root, "dec-1", SESSION)
        with self.assertRaisesRegex(ValueError, "not in the approved outputs"):
            approvals.require_proposal_approved(self.root, rec, SESSION, "P2")
        with self.assertRaisesRegex(ValueError, "not in the approved outputs|not exactly one"):
            approvals.require_proposal_approved(self.root, rec, SESSION, "P9")

    def test_proposal_hash_not_in_handoff_refused(self):
        folder = self.root / self.base
        self.write_handoff(["proposals/index.json", "proposals/P2_seed_genes.csv"])
        self.add({"id": "dec-2", "kind": "stage_approval", "stage": "data", "session_id": SESSION,
                  "outputs": ["P1"], "artifact": self.ref()})
        rec = approvals.require_data_approval(self.root, "dec-2", SESSION)
        with self.assertRaisesRegex(ValueError, "not an artifact of the approved handoff"):
            approvals.require_proposal_approved(self.root, rec, SESSION, "P1")

    def test_mapping_approval_ok_and_mismatch_refused(self):
        (self.root / "mapping.json").write_text("{}")
        digest = sha(self.root / "mapping.json")
        ref = {"path": "mapping.json", "sha256": digest}
        self.add({"id": "map-1", "kind": "stage_approval", "stage": "data_mapping", "session_id": SESSION,
                  "outputs": ["mapping"], "artifact": ref})
        self.assertEqual(approvals.require_mapping_approval(self.root, "map-1", "mapping.json", digest)["id"], "map-1")
        with self.assertRaisesRegex(ValueError, "sha256"):
            approvals.require_mapping_approval(self.root, "map-1", "mapping.json", "0" * 64)
        with self.assertRaisesRegex(ValueError, "artifact must be"):
            approvals.require_mapping_approval(self.root, "map-1", "other.json", digest)
        with self.assertRaisesRegex(ValueError, "data_mapping"):
            approvals.require_mapping_approval(self.root, "dec-1", "mapping.json", digest)
        (self.root / "mapping.json").write_text("{ }")
        with self.assertRaisesRegex(ValueError, "changed since approval"):
            approvals.require_mapping_approval(self.root, "map-1", "mapping.json", digest)

    def test_state_accepts_data_mapping_stage(self):
        (self.root / "m.json").write_text("{}")
        ref = {"path": "m.json", "sha256": sha(self.root / "m.json")}
        state.validate_record(self.root, {"id": "x", "kind": "stage_approval", "stage": "data_mapping",
                                          "session_id": SESSION, "approved_by": "researcher",
                                          "authorization": "ok", "outputs": ["m"], "artifact": ref})
        with self.assertRaisesRegex(ValueError, "unknown scientific stage"):
            state.validate_record(self.root, {"id": "x", "kind": "stage_approval", "stage": "bogus",
                                              "session_id": SESSION, "approved_by": "researcher",
                                              "authorization": "ok", "outputs": ["m"], "artifact": ref})


if __name__ == "__main__":
    unittest.main()

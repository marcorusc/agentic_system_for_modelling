from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts import state
from scripts.capture.record_invocation import record
from scripts.data import handoff, manifest, mapping, receive, session
from scripts.data.common import session_dir, sha256_file
from scripts.validate.evaluate import evaluate
from tests.data.test_record_invocation_data import transcript_events

AID = "a1b2c3"
NEKO = "neko-session-1"
BNET = f"runs/network-curator/{NEKO}/exports/inv1/model.bnet"
BNET_TEXT = "targets, factors\n# exported\n\nEGFR, EGFR\nMAPK1, EGFR\nProliferation, MAPK1\nSurvival, MAPK1\n"
PERTURBATIONS = ("scenario_id,context,entity,entity_type,targets,effect,evidence\n"
                 "S1,LUAD,erlotinib,compound,EGFR,inhibit,GDSC\n"
                 "S2,LUAD,trametinib,compound,MAP2K1;MAP2K2,inhibit,GDSC\n")
TARGETS = ("target_id,statement,test_context,reference_context,perturbation,phenotype,expected,"
           "evidence_strength,evidence\n"
           "V1,EGFR-mutant drop larger,LUAD_EGFR,LUAD_wt,S1,viability,greater_drop,moderate,GDSC\n"
           "V2,MEK drop,LUAD_EGFR,LUAD_wt,S2,viability,greater_drop,weak,GDSC\n")
SEEDS = "hgnc_symbol,tier,evidence\nEGFR,core,lit\n"
SOURCE = "inputs/papers/smith2024.pdf"
SOURCE_BYTES = b"%PDF-1.4 synthetic figure source\n"
STANDALONE_BNET = "inputs/models/user.bnet"
STANDALONE_OUTPUTS = ["Proliferation", "Survival"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class MappingFixture(unittest.TestCase):
    """A real data session (manifest, handoff, recorder integrity) with an approval record."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root, self.troot = base / "project", base / "transcripts"
        self.root.mkdir()
        self.troot.mkdir()
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        shutil.copyfile(state.ROOT / "templates" / "DECISIONS.md", self.root / "DECISIONS.md")
        shutil.copyfile(state.ROOT / "templates" / "VALIDATION_CRITERIA.yaml", self.root / "VALIDATION_CRITERIA.yaml")
        (self.root / "setup").mkdir()
        (self.root / "setup" / "data-requirements.lock").write_text("pkg==1\n", encoding="utf-8")
        (self.root / ".venv-data" / "bin").mkdir(parents=True)
        (self.root / ".venv-data" / "bin" / "python").symlink_to(sys.executable)
        (self.root / "scripts" / "data").mkdir(parents=True)
        (self.root / "scripts" / "data" / "session.py").write_text("")
        self.sid, digest = session.new_session(self.root, "x", None)
        self.dir = session_dir(self.root, self.sid)
        self.base = f"runs/data-analyst/{self.sid}"
        files = {"P1": ("perturbations", "maboss", PERTURBATIONS), "P2": ("validation_targets", "maboss", TARGETS),
                 "P3": ("seed_genes", "neko", SEEDS),
                 "P4": ("seed_genes", "neko", "hgnc_symbol,tier,evidence\nMAPK1,core,lit\n")}
        index = []
        for pid, (kind, layer, text) in files.items():
            (self.dir / "proposals" / f"{pid}_{kind}.csv").write_text(text, encoding="utf-8")
            index.append({"id": pid, "kind": kind, "target_layer": layer, "path": f"proposals/{pid}_{kind}.csv"})
        (self.dir / "proposals" / "index.json").write_text(json.dumps(index), encoding="utf-8")
        manifest.build(self.root, self.sid, [])
        (self.dir / "handoff_notes.json").write_text("{}", encoding="utf-8")
        handoff.build(self.root, self.sid, "needs_approval", "handoff_notes.json")
        directory = self.troot / receive.project_slug(self.root) / "uuid-1" / "subagents"
        directory.mkdir(parents=True)
        rel = f"{self.base}/handoff.json"
        report = f"# Report\n\nHandoff: {rel} sha256={sha256_file(self.root / rel)}"
        events = transcript_events(self.sid, digest) + [
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t9", "name": "SubagentHandback", "input": {"message": report}}]}}]
        transcript = directory / f"agent-{AID}.jsonl"
        transcript.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        record(self.root, {"agent_type": "data-analyst", "agent_id": AID, "agent_transcript_path": str(transcript)})
        self.approve("dec-data-1", ["P1", "P2", "P3"])
        bnet = self.root / BNET
        bnet.parent.mkdir(parents=True)
        bnet.write_text(BNET_TEXT, encoding="utf-8")

    def approve(self, record_id, outputs):
        ref = {"path": f"{self.base}/handoff.json", "sha256": sha(self.root / self.base / "handoff.json")}
        state.update(self.root, "record", {"id": record_id, "kind": "stage_approval", "stage": "data",
                                           "session_id": self.sid, "outputs": outputs, "artifact": ref,
                                           "approved_by": "researcher", "authorization": "researcher: ok"})

    def draft(self, purpose="luad", proposals=("P1", "P2"), approval="dec-data-1"):
        path = mapping.draft(self.root, purpose, [(self.sid, p, approval) for p in proposals], (NEKO, BNET))
        return path.relative_to(self.root).as_posix()

    def load(self, rel):
        return json.loads((self.root / rel).read_text(encoding="utf-8"))

    def save(self, rel, data):
        (self.root / rel).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def complete(self, purpose="luad"):
        rel = self.draft(purpose)
        data = self.load(rel)
        data["contexts"] = {"LUAD_EGFR": [{"node": "EGFR", "state": 1}], "LUAD_wt": []}
        data["perturbations"] = [{"id": "S1", "from": {"proposal": "P1", "row": "S1"},
                                  "model": [{"node": "EGFR", "state": 0}], "note": "erlotinib -> EGFR off"}]
        data["readouts"] = [{"phenotype": "viability", "nodes": ["Proliferation", "Survival"]}]
        data["criteria"] = [{"criterion_id": "V1", "from": {"proposal": "P2", "row": "V1"},
                             "method": "scenario_contrast",
                             "test": {"context": "LUAD_EGFR", "perturbation": "S1"},
                             "reference": {"context": "LUAD_wt", "perturbation": "S1"},
                             "options": {"readouts": ["Proliferation"], "margin": 0.05, "combine": "all",
                                         "statistic": "tail_mean", "tail_points": 2}}]
        data["unmapped"] = [{"from": {"proposal": "P1", "row": "S2"}, "reason": "MEK is not a model node"},
                            {"from": {"proposal": "P2", "row": "V2"}, "reason": "depends on unmapped S2"}]
        self.save(rel, data)
        return rel, data

    def add_source(self, rel=SOURCE, content=SOURCE_BYTES):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return rel

    def add_standalone(self, record_id="sa-1", rel=STANDALONE_BNET, text=BNET_TEXT, kind="standalone_approval",
                       stage="boolean-dynamics"):
        """A researcher-provided BNET with an explicit standalone authorization record."""
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(text, encoding="utf-8")
        item = {"id": record_id, "kind": kind, "stage": stage, "outputs": STANDALONE_OUTPUTS,
                "artifact": {"path": rel, "sha256": sha(path)}, "approved_by": "researcher",
                "authorization": "researcher: use my model"}
        if kind == "stage_approval":
            item["session_id"] = NEKO
        state.update(self.root, "record", item)
        return rel

    def complete_sources(self, purpose="papers", network=None, sources=(("smith2024", SOURCE),)):
        """A mapping whose only inputs are researcher-provided sources."""
        for _, rel in sources:
            if not (self.root / rel).exists():
                self.add_source(rel)
        path = mapping.draft(self.root, purpose, [], network or (NEKO, BNET), sources=list(sources))
        rel = path.relative_to(self.root).as_posix()
        data = self.load(rel)
        data["contexts"] = {"LUAD_EGFR": [{"node": "EGFR", "state": 1}], "LUAD_wt": []}
        data["perturbations"] = [{"id": "S1", "from": {"source": "smith2024", "locator": "Fig. 3B"},
                                  "model": [{"node": "EGFR", "state": 0}]}]
        data["readouts"] = [{"phenotype": "viability", "nodes": ["Proliferation", "Survival"]}]
        data["criteria"] = [{"criterion_id": "V1", "from": [{"source": "smith2024", "locator": "Fig. 3C"},
                                                            {"source": "smith2024", "locator": "Table S2, EGFR row"}],
                             "method": "scenario_contrast",
                             "test": {"context": "LUAD_EGFR", "perturbation": "S1"},
                             "reference": {"context": "LUAD_wt", "perturbation": "S1"},
                             "options": {"readouts": ["Proliferation"], "margin": 0.05, "combine": "all",
                                         "statistic": "tail_mean", "tail_points": 2}}]
        self.save(rel, data)
        return rel, data

    def errors_after(self, rel, data, change):
        data = copy.deepcopy(data)
        change(data)
        self.save(rel, data)
        return mapping.check(self.root, rel)

    def assertError(self, errors, *fragments):
        for fragment in fragments:
            self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} not in {errors}")


class BnetTests(unittest.TestCase):
    def test_bnet_nodes_skip_header_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.bnet"
            path.write_text("  TARGETS ,   Factors  \n# A, B\n\n  A , B & C\nB,A\r\nC , !A\n", encoding="utf-8")
            self.assertEqual(mapping.bnet_nodes(path), {"A", "B", "C"})
            path.write_text("targets,factors\nA B\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                mapping.bnet_nodes(path)


class DraftTests(MappingFixture):
    def test_draft_fills_inputs_and_unmapped(self):
        rel = self.draft()
        self.assertEqual(rel, "runs/orchestrator/luad/mapping.json")
        data = self.load(rel)
        self.assertEqual(set(data), {"schema_version", "inputs", "contexts", "perturbations", "readouts",
                                     "criteria", "unmapped"})
        self.assertIs(type(data["schema_version"]), int)
        p1 = f"{self.base}/proposals/P1_perturbations.csv"
        self.assertEqual(data["inputs"]["data"][0], {"session": self.sid, "proposal": "P1", "path": p1,
                                                     "sha256": sha(self.root / p1), "approval": "dec-data-1"})
        self.assertEqual(data["inputs"]["network"], {"neko_session": NEKO, "bnet": BNET, "sha256": sha(self.root / BNET)})
        self.assertEqual((data["contexts"], data["perturbations"], data["readouts"], data["criteria"]), ({}, [], [], []))
        self.assertEqual(data["unmapped"], [{"from": {"proposal": p, "row": r}, "reason": "TODO"}
                                            for p, r in (("P1", "S1"), ("P1", "S2"), ("P2", "V1"), ("P2", "V2"))])
        with self.assertRaisesRegex(ValueError, "exists"):
            self.draft()
        # The skeleton itself fails check only on TODO reasons.
        errors = mapping.check(self.root, rel)
        self.assertEqual(len(errors), 4, errors)
        self.assertError(errors, "TODO")

    def test_draft_refuses_unapproved(self):
        self.approve("dec-data-2", ["P2"])
        with self.assertRaisesRegex(ValueError, "not in the approved outputs"):
            self.draft(approval="dec-data-2")
        with self.assertRaisesRegex(ValueError, "not found"):
            self.draft(approval="nope")
        with self.assertRaisesRegex(ValueError, "seed_genes"):
            self.draft(proposals=("P1", "P3"))
        with self.assertRaisesRegex(ValueError, "runs/network-curator"):
            mapping.draft(self.root, "x", [(self.sid, "P1", "dec-data-1")], ("other-neko", BNET))
        self.assertFalse((self.root / "runs/orchestrator/luad/mapping.json").exists())


class CheckTests(MappingFixture):
    def setUp(self):
        super().setUp()
        self.rel, self.data = self.complete()

    def test_overlap_of_context_and_perturbation_is_a_note_not_an_error(self):
        rel, data = self.complete("overlap")
        self.assertEqual(mapping.check(self.root, rel), [])
        self.assertEqual(mapping.overlaps(data), [("S1", "LUAD_EGFR", "EGFR")])
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = mapping.main(["check", rel])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("note: perturbation S1 overrides context LUAD_EGFR on EGFR", out.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_bnet_may_be_a_captured_boolean_handoff(self):
        rel, data = self.complete("captured")
        captured = f"runs/network-curator/{NEKO}/boolean-handoffs/cap-1/model.bnet"
        (self.root / captured).parent.mkdir(parents=True)
        (self.root / captured).write_text(BNET_TEXT, encoding="utf-8")
        data["inputs"]["network"] = {"neko_session": NEKO, "bnet": captured, "sha256": sha(self.root / captured)}
        self.save(rel, data)
        self.assertEqual(mapping.check(self.root, rel), [])
        data["inputs"]["network"]["bnet"] = f"runs/network-curator/{NEKO}/other/model.bnet"
        self.save(rel, data)
        self.assertError(mapping.check(self.root, rel), "network BNET must be")

    def test_check_complete_mapping_passes(self):
        self.assertEqual(mapping.check(self.root, self.rel), [])

    def test_public_load_and_check_and_validate_data_handoff(self):
        data, digest, errors = mapping.load_and_check(self.root, self.rel)
        self.assertEqual((data, digest, errors), (self.data, sha(self.root / self.rel), []))
        draft = self.draft("todo")
        self.assertEqual(len(mapping.load_and_check(self.root, draft)[2]), 4)
        with self.assertRaises(ValueError):
            mapping.load_and_check(self.root, "runs/elsewhere/m.json")
        mapping.validate_data_handoff(self.root, self.sid)
        handoff_path = self.root / self.base / "handoff.json"
        handoff_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no longer validates"):
            mapping.validate_data_handoff(self.root, self.sid)

    def test_hash_mismatch(self):
        errors = self.errors_after(self.rel, self.data, lambda d: d["inputs"]["data"][0].update(sha256="0" * 64))
        self.assertError(errors, "sha256")
        self.save(self.rel, self.data)
        (self.root / BNET).write_text(BNET_TEXT + "Extra, EGFR\n", encoding="utf-8")
        self.assertError(mapping.check(self.root, self.rel), BNET)

    def test_unknown_node(self):
        def change(d):
            d["contexts"]["LUAD_wt"] = [{"node": "KRAS", "state": 1}]
            d["perturbations"][0]["model"][0]["node"] = "ERBB2"
            d["readouts"][0]["nodes"].append("Apoptosis")
        errors = self.errors_after(self.rel, self.data, change)
        self.assertError(errors, "KRAS", "ERBB2", "Apoptosis")
        errors = self.errors_after(self.rel, self.data, lambda d: d["contexts"]["LUAD_wt"].append({"node": "EGFR", "state": 2}))
        self.assertError(errors, "state")

    def test_missing_row_rejected(self):
        errors = self.errors_after(self.rel, self.data, lambda d: d["unmapped"].pop())
        self.assertError(errors, "V2")
        errors = self.errors_after(self.rel, self.data, lambda d: d["unmapped"][0]["from"].update(row="S9"))
        self.assertError(errors, "S9", "S2")

    def test_row_mapped_twice_or_also_unmapped_rejected(self):
        errors = self.errors_after(self.rel, self.data, lambda d: d["unmapped"].append(
            {"from": {"proposal": "P1", "row": "S1"}, "reason": "also unmapped"}))
        self.assertError(errors, "P1 row S1")
        twice = copy.deepcopy(self.data["perturbations"][0])
        twice["id"] = "S1b"
        errors = self.errors_after(self.rel, self.data, lambda d: d["perturbations"].append(twice))
        self.assertError(errors, "P1 row S1")

    def test_todo_reason_rejected(self):
        for reason in ("TODO", " todo ", "", None):
            errors = self.errors_after(self.rel, self.data, lambda d: d["unmapped"][0].update(reason=reason))
            self.assertError(errors, "reason")

    def test_undefined_context_rejected(self):
        def change(d):
            d["criteria"][0]["test"]["context"] = "BRCA"
            d["criteria"][0]["reference"]["perturbation"] = "S7"
        errors = self.errors_after(self.rel, self.data, change)
        self.assertError(errors, "BRCA", "S7")
        dup = {"id": "S1", "from": {"proposal": "P1", "row": "S2"}, "model": [{"node": "MAPK1", "state": 0}]}
        errors = self.errors_after(self.rel, self.data, lambda d: (d["perturbations"].append(dup), d["unmapped"].pop(0)))
        self.assertError(errors, "duplicate perturbation id S1")

    def test_bad_method_or_options_rejected(self):
        errors = self.errors_after(self.rel, self.data, lambda d: d["criteria"][0].update(method="magic"))
        self.assertError(errors, "magic")
        for bad in ({"margin": -1}, {"combine": "most"}, {"statistic": "final"}, {"tail_points": 0}, {"extra": 1}):
            errors = self.errors_after(self.rel, self.data, lambda d: d["criteria"][0]["options"].update(bad))
            self.assertError(errors, "options")
        peaks = {"criterion_id": "V2", "from": {"proposal": "P2", "row": "V2"}, "method": "ordered_peaks",
                 "scenarios": [{"context": "LUAD_EGFR", "perturbation": None}],
                 "options": {"nodes": ["Proliferation", "Survival"], "comparators": ["<"], "metric": "bogus"}}
        errors = self.errors_after(self.rel, self.data, lambda d: (d["criteria"].append(peaks), d["unmapped"].pop()))
        self.assertError(errors, "V2", "options")
        peaks = copy.deepcopy(peaks)
        peaks["options"].update(metric="first_peak", drop=0.1)
        errors = self.errors_after(self.rel, self.data, lambda d: (d["criteria"].append(peaks), d["unmapped"].pop()))
        self.assertEqual(errors, [])
        dup = copy.deepcopy(self.data["criteria"][0])
        dup["from"] = {"proposal": "P2", "row": "V2"}
        errors = self.errors_after(self.rel, self.data, lambda d: (d["criteria"].append(dup), d["unmapped"].pop()))
        self.assertError(errors, "duplicate criterion id V1")
        errors = self.errors_after(self.rel, self.data, lambda d: d["criteria"][0].update(
            reference={"context": "LUAD_EGFR", "perturbation": "S1"}))
        self.assertError(errors, "context")
        errors = self.errors_after(self.rel, self.data, lambda d: d["criteria"][0]["from"].update(proposal="P1", row="S2"))
        self.assertError(errors, "validation_targets")

    def test_boolean_structure_rejected(self):
        structure = {"criterion_id": "V2", "from": {"proposal": "P2", "row": "V2"}, "method": "boolean_structure",
                     "options": {"analysis": "fixed_points", "max_states": 16, "expected_count": 1}}
        errors = self.errors_after(self.rel, self.data, lambda d: (d["criteria"].append(structure), d["unmapped"].pop()))
        self.assertError(errors, "boolean_structure is not allowed in a data mapping")

    def test_readout_not_declared_rejected(self):
        errors = self.errors_after(self.rel, self.data, lambda d: d["criteria"][0]["options"].update(readouts=["MAPK1"]))
        self.assertError(errors, "MAPK1")
        self.assertTrue(all("options" not in e for e in errors), errors)

    def test_seed_genes_input_rejected(self):
        p3 = f"{self.base}/proposals/P3_seed_genes.csv"
        entry = {"session": self.sid, "proposal": "P3", "path": p3, "sha256": sha(self.root / p3), "approval": "dec-data-1"}
        errors = self.errors_after(self.rel, self.data, lambda d: d["inputs"]["data"].append(entry))
        self.assertError(errors, "seed_genes")

    def test_unapproved_input_rejected(self):
        self.approve("dec-data-2", ["P2"])
        errors = self.errors_after(self.rel, self.data, lambda d: d["inputs"]["data"][0].update(approval="dec-data-2"))
        self.assertError(errors, "not in the approved outputs")
        h = self.root / self.base / "handoff.json"
        self.save(self.rel, self.data)
        h.write_text(h.read_text() + " ")
        self.assertError(mapping.check(self.root, self.rel), "changed since approval")

    def test_canonical_cycles_options(self):
        cycles = {"criterion_id": "V2", "from": {"proposal": "P2", "row": "V2"}, "method": "canonical_cycles",
                  "scenarios": [{"context": "LUAD_wt", "perturbation": None}],
                  "options": {"activation_order": ["EGFR", "MAPK1", "Proliferation"], "onset_node": "Survival",
                              "reset_node": "EGFR", "threshold": 0.5, "sample_count": 1, "minimum_canonical": 1,
                              "minimum_fraction": 0.5}}
        def add(d, c):
            d["criteria"].append(c)
            d["unmapped"].pop()
            d["readouts"].append({"phenotype": "other", "nodes": ["EGFR", "MAPK1"]})
        self.assertEqual(self.errors_after(self.rel, self.data, lambda d: add(d, cycles)), [])
        bad = copy.deepcopy(cycles)
        bad["options"]["threshold"] = 2
        self.assertError(self.errors_after(self.rel, self.data, lambda d: add(d, bad)), "invalid canonical_cycles options")

    def test_check_lists_all_problems(self):
        def change(d):
            d["unmapped"][0]["reason"] = "TODO"
            d["contexts"]["LUAD_wt"] = [{"node": "KRAS", "state": 1}]
            d["criteria"][0]["options"]["margin"] = -1
        self.assertGreaterEqual(len(self.errors_after(self.rel, self.data, change)), 3)
        errors = self.errors_after(self.rel, self.data, lambda d: d.update(extra=1))
        self.assertError(errors, "keys")
        (self.root / self.rel).write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
        self.assertError(mapping.check(self.root, self.rel), "duplicate")
        self.assertError(mapping.check(self.root, "runs/elsewhere/mapping.json"), "runs/orchestrator")


class CriteriaTests(MappingFixture):
    def setUp(self):
        super().setUp()
        self.rel, self.data = self.complete()
        self.trajectories = {}
        values = {("LUAD_EGFR", None): 0.9, ("LUAD_EGFR", "S1"): 0.2, ("LUAD_wt", None): 0.6, ("LUAD_wt", "S1"): 0.5}
        runs = []
        for n, ((context, pert), value) in enumerate(values.items()):
            rel = f"runs/boolean-dynamics-modeler/mb-1/exports/inv1/run{n}.csv"
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"Time,Proliferation\n0,0.5\n1,{value}\n2,{value}\n", encoding="utf-8")
            self.trajectories[(context, pert)] = rel
            runs.append({"context": context, "perturbation": pert, "trajectory": rel})
        self.runs_rel = "runs/orchestrator/luad/runs.json"
        self.save(self.runs_rel, {"runs": runs})
        self.approve_mapping("dec-map-1")

    def approve_mapping(self, record_id, rel=None):
        rel = rel or self.rel
        state.update(self.root, "record", {
            "id": record_id, "kind": "stage_approval", "stage": "data_mapping", "session_id": NEKO,
            "outputs": ["S1", "V1"], "artifact": {"path": rel, "sha256": sha(self.root / rel)},
            "approved_by": "researcher", "authorization": "researcher: mapping ok"})

    def test_criteria_scenario_contrast_input_order(self):
        result = mapping.criteria(self.root, self.rel, self.runs_rel, "dec-map-1")
        (entry,) = result["criteria"]
        t = self.trajectories
        self.assertEqual(entry, {"criterion_id": "V1", "method": "scenario_contrast",
                                 "inputs": [t[("LUAD_EGFR", None)], t[("LUAD_EGFR", "S1")],
                                            t[("LUAD_wt", None)], t[("LUAD_wt", "S1")]],
                                 "options": self.data["criteria"][0]["options"]})
        (decl,) = result["declarations"]
        self.assertEqual(set(decl), {"Criterion", "Method", "Required evidence"})
        self.assertEqual((decl["Criterion"], decl["Method"]), ("V1", "scenario_contrast"))
        self.assertIn(self.rel, decl["Required evidence"])
        self.assertIn("approval dec-map-1", decl["Required evidence"])
        self.save("VALIDATION_CRITERIA.yaml", {"schema_version": 1, "criteria": result["criteria"]})
        report = evaluate(self.root, "VALIDATION_CRITERIA.yaml")
        self.assertEqual(report["results"][0]["status"], "passed", report)

    def test_criteria_require_mapping_approval(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            mapping.criteria(self.root, self.rel, self.runs_rel, "nope")
        with self.assertRaisesRegex(ValueError, "data_mapping"):
            mapping.criteria(self.root, self.rel, self.runs_rel, "dec-data-1")
        # Edited after approval.
        edited = dict(self.data, unmapped=self.data["unmapped"][:1])
        self.save(self.rel, edited)
        with self.assertRaisesRegex(ValueError, "approves a different sha256"):
            mapping.criteria(self.root, self.rel, self.runs_rel, "dec-map-1")

    def test_cli_criteria_needs_approval_and_failed_out_leaves_yaml_untouched(self):
        def run(*argv):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = mapping.main(list(argv))
            return code, out.getvalue(), err.getvalue()
        yaml = self.root / "VALIDATION_CRITERIA.yaml"
        before = yaml.read_bytes()
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                mapping.main(["criteria", self.rel, "--runs", self.runs_rel, "--merge-into", "VALIDATION_CRITERIA.yaml"])
        code, _, err = run("criteria", self.rel, "--runs", self.runs_rel, "--approval", "nope")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)
        # --out cannot be written (its parent is a file): the YAML must stay untouched.
        code, _, err = run("criteria", self.rel, "--runs", self.runs_rel, "--approval", "dec-map-1",
                           "--out", "runs/orchestrator/luad/runs.json/criteria.json", "--merge-into", "VALIDATION_CRITERIA.yaml")
        self.assertEqual(code, 1, err)
        self.assertEqual(yaml.read_bytes(), before)
        code, out, err = run("criteria", self.rel, "--runs", self.runs_rel, "--approval", "dec-map-1")
        self.assertEqual(code, 0, err)
        self.assertIn("approval dec-map-1", out)

    def test_criteria_missing_run_refused(self):
        runs = self.load(self.runs_rel)
        runs["runs"] = [r for r in runs["runs"] if (r["context"], r["perturbation"]) != ("LUAD_wt", None)]
        self.save(self.runs_rel, runs)
        with self.assertRaisesRegex(ValueError, "LUAD_wt"):
            mapping.criteria(self.root, self.rel, self.runs_rel, "dec-map-1")
        runs["runs"].append({"context": "LUAD_wt", "perturbation": None, "trajectory": "outside.csv"})
        (self.root / "outside.csv").write_text("Time,Proliferation\n0,0.5\n", encoding="utf-8")
        self.save(self.runs_rel, runs)
        with self.assertRaisesRegex(ValueError, "runs/boolean-dynamics-modeler"):
            mapping.criteria(self.root, self.rel, self.runs_rel, "dec-map-1")

    def test_merge_refuses_duplicate_id(self):
        entries = mapping.criteria(self.root, self.rel, self.runs_rel, "dec-map-1")["criteria"]
        mapping.merge_into(self.root, "VALIDATION_CRITERIA.yaml", entries)
        merged = self.load("VALIDATION_CRITERIA.yaml")
        self.assertEqual(merged, {"schema_version": 1, "criteria": entries})
        before = (self.root / "VALIDATION_CRITERIA.yaml").read_bytes()
        with self.assertRaisesRegex(ValueError, "V1"):
            mapping.merge_into(self.root, "VALIDATION_CRITERIA.yaml", entries)
        self.assertEqual((self.root / "VALIDATION_CRITERIA.yaml").read_bytes(), before)

    def test_merge_preserves_mode(self):
        target = self.root / "VALIDATION_CRITERIA.yaml"
        target.chmod(0o644)
        entries = mapping.criteria(self.root, self.rel, self.runs_rel, "dec-map-1")["criteria"]
        mapping.merge_into(self.root, "VALIDATION_CRITERIA.yaml", entries)
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)

    def test_criteria_duplicate_trajectory_refused(self):
        runs = self.load(self.runs_rel)
        runs["runs"][3]["trajectory"] = runs["runs"][2]["trajectory"]
        self.save(self.runs_rel, runs)
        with self.assertRaisesRegex(ValueError, "same trajectory"):
            mapping.criteria(self.root, self.rel, self.runs_rel, "dec-map-1")

    def test_cli_exit_codes(self):
        def run(*argv):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = mapping.main(list(argv))
            return code, out.getvalue(), err.getvalue()
        code, out, err = run("check", self.rel)
        self.assertEqual(code, 0, err)
        code, out, err = run("criteria", self.rel, "--runs", self.runs_rel, "--approval", "dec-map-1",
                             "--merge-into", "VALIDATION_CRITERIA.yaml")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["criteria"][0]["criterion_id"], "V1")
        self.assertEqual(self.load("VALIDATION_CRITERIA.yaml")["criteria"][0]["criterion_id"], "V1")
        code, out, err = run("criteria", self.rel, "--runs", self.runs_rel, "--approval", "dec-map-1",
                             "--out", "runs/orchestrator/luad/criteria.json")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load("runs/orchestrator/luad/criteria.json")["criteria"][0]["criterion_id"], "V1")
        code, out, err = run("criteria", self.rel, "--runs", self.runs_rel, "--approval", "dec-map-1",
                             "--merge-into", "VALIDATION_CRITERIA.yaml")
        self.assertEqual(code, 1)
        bad = copy.deepcopy(self.data)
        bad["unmapped"][0]["reason"] = "TODO"
        bad["contexts"]["LUAD_wt"] = [{"node": "KRAS", "state": 1}]
        self.save(self.rel, bad)
        code, out, err = run("check", self.rel)
        self.assertEqual(code, 1)
        self.assertGreaterEqual(len(err.strip().split("\n")), 2, err)
        code, out, err = run("draft", "--purpose", "brca", "--data", f"{self.sid}:P1:dec-data-1",
                             "--network", f"{NEKO}:{BNET}")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "runs/orchestrator/brca/mapping.json").is_file())
        code, out, err = run("draft", "--purpose", "brca", "--data", f"{self.sid}:P1:dec-data-1",
                             "--network", f"{NEKO}:{BNET}")
        self.assertEqual(code, 1)
        code, out, err = run("draft", "--purpose", "x2", "--data", f"{self.sid}:P1", "--network", f"{NEKO}:{BNET}")
        self.assertEqual(code, 1)


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = mapping.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class SourceTests(MappingFixture):
    """A. Researcher-provided sources (any format, under inputs/) cited with a locator."""

    def test_sources_only_mapping_passes(self):
        rel, data = self.complete_sources()
        self.assertEqual(data["inputs"]["data"], [])
        self.assertEqual(data["inputs"]["sources"], [{"id": "smith2024", "path": SOURCE,
                                                       "sha256": sha(self.root / SOURCE)}])
        self.assertEqual(data["unmapped"], [])
        self.assertEqual(mapping.check(self.root, rel), [])

    def test_draft_needs_data_or_source_and_existing_sources(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            mapping.draft(self.root, "none", [], (NEKO, BNET), sources=[])
        with self.assertRaisesRegex(ValueError, "missing"):
            mapping.draft(self.root, "gone", [], (NEKO, BNET), sources=[("x", "inputs/absent.pdf")])
        self.add_source()
        with self.assertRaisesRegex(ValueError, "twice"):
            mapping.draft(self.root, "dup", [], (NEKO, BNET), sources=[("a", SOURCE), ("a", SOURCE)])
        self.assertFalse((self.root / "runs/orchestrator/dup").exists())

    def test_uncited_source_refused(self):
        rel, data = self.complete_sources()
        other = self.add_source("inputs/tables/viability.xlsx", b"PK\x03\x04 fake workbook")
        extra = {"id": "viability", "path": other, "sha256": sha(self.root / other)}
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["sources"].append(extra))
        self.assertEqual(errors, ["source viability is never cited"])

    def test_unknown_source_id_refused(self):
        rel, data = self.complete_sources()
        errors = self.errors_after(rel, data, lambda d: d["perturbations"][0]["from"].update(source="nope"))
        self.assertError(errors, "source nope is not declared")

    def test_empty_locator_refused(self):
        rel, data = self.complete_sources()
        for locator in ("", "   ", None, 3, "Fig. 1 | row 2", "Fig. 1\nrow 2"):
            errors = self.errors_after(rel, data, lambda d: d["perturbations"][0]["from"].update(locator=locator))
            self.assertError(errors, "locator")

    def test_locator_and_path_control_or_line_break_characters_refused(self):
        rel, data = self.complete_sources()
        bad_chars = ("\u2028", "\x0c", "\x85", "\x00", "\u2029", "\x0b", "\x1e", "\t")
        for char in bad_chars:
            locator = f"Fig. 1{char}row 2"
            errors = self.errors_after(rel, data, lambda d: d["perturbations"][0]["from"].update(locator=locator))
            self.assertError(errors, "locator")
        for name in [f"inputs/a{char}b.pdf" for char in bad_chars] + ["inputs/a|b.pdf"]:
            if "\x00" not in name:
                self.add_source(name)
            errors = self.errors_after(rel, data, lambda d: d["inputs"]["sources"][0].update(path=name))
            self.assertError(errors, "inputs.sources[0]", "character")
        with self.assertRaisesRegex(ValueError, "character"):
            mapping.draft(self.root, "ctl", [], (NEKO, BNET), sources=[("x", self.add_source("inputs/a\u2028b.pdf"))])
        # Ordinary spaces and non-ASCII letters remain allowed in locators and paths.
        spaced = self.add_source("inputs/papers/Müller et al 2024.pdf")
        def change(d):
            d["inputs"]["sources"][0].update(path=spaced, sha256=sha(self.root / spaced))
            d["perturbations"][0]["from"].update(locator="Abb. 3B, Zeile «KRAS»")
        self.assertEqual(self.errors_after(rel, data, change), [])

    def test_source_outside_inputs_refused(self):
        rel, data = self.complete_sources()
        outside = "runs/orchestrator/notes.txt"
        (self.root / outside).write_text("x", encoding="utf-8")
        (self.root / "inputs" / "folder").mkdir()
        for path in (outside, "inputs", "inputs/folder", "./" + SOURCE, "inputs//papers/smith2024.pdf",
                     "inputs/../" + outside, str(self.root / SOURCE), "inputs\\papers\\smith2024.pdf"):
            errors = self.errors_after(rel, data, lambda d: d["inputs"]["sources"][0].update(path=path))
            self.assertError(errors, "inputs.sources[0]")
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["sources"][0].update(path="inputs/folder"))
        self.assertError(errors, "folder")

    def test_symlinked_source_refused(self):
        rel, data = self.complete_sources()
        (self.root / "inputs" / "link.pdf").symlink_to(self.root / SOURCE)
        (self.root / "inputs" / "linkdir").symlink_to(self.root / "inputs" / "papers")
        for path in ("inputs/link.pdf", "inputs/linkdir/smith2024.pdf"):
            errors = self.errors_after(rel, data, lambda d: d["inputs"]["sources"][0].update(path=path))
            self.assertError(errors, "symlink")

    def test_source_hash_mismatch_refused(self):
        rel, data = self.complete_sources()
        (self.root / SOURCE).write_bytes(SOURCE_BYTES + b"edited")
        self.assertError(mapping.check(self.root, rel), "inputs.sources[0]", "sha256")
        self.add_source()
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["sources"][0].update(sha256="A" * 64))
        self.assertError(errors, "sha256")

    def test_source_declaration_shape(self):
        rel, data = self.complete_sources()
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["sources"][0].update(id="bad id"))
        self.assertError(errors, "safe identifier")
        twice = dict(data["inputs"]["sources"][0])
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["sources"].append(twice))
        self.assertError(errors, "duplicate source id smith2024")
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["sources"][0].update(extra=1))
        self.assertError(errors, "id, path, sha256")
        errors = self.errors_after(rel, data, lambda d: d["inputs"].pop("sources"))
        self.assertError(errors, "inputs must have exactly the keys data, sources and network")
        errors = self.errors_after(rel, data, lambda d: d["inputs"].update(sources=[]))
        self.assertError(errors, "cannot both be empty")

    def test_mixed_proposal_and_source_refs(self):
        rel, data = self.complete()
        self.add_source()
        source = {"id": "smith2024", "path": SOURCE, "sha256": sha(self.root / SOURCE)}

        def change(d):
            d["inputs"]["sources"].append(source)
            d["perturbations"][0]["from"] = [{"proposal": "P1", "row": "S1"},
                                             {"source": "smith2024", "locator": "Fig. 2A"}]
        self.assertEqual(self.errors_after(rel, data, change), [])

        def twice(d):
            change(d)
            d["criteria"][0]["from"] = [{"proposal": "P2", "row": "V1"}, {"proposal": "P1", "row": "S1"}]
        self.assertError(self.errors_after(rel, data, twice), "P1 row S1 is referenced 2 times", "validation_targets")

    def test_from_as_list(self):
        rel, data = self.complete()

        def both_rows(d):
            d["perturbations"][0]["from"] = [{"proposal": "P1", "row": "S1"}, {"proposal": "P1", "row": "S2"}]
            d["unmapped"] = [u for u in d["unmapped"] if u["from"] != {"proposal": "P1", "row": "S2"}]
        self.assertEqual(self.errors_after(rel, data, both_rows), [])
        errors = self.errors_after(rel, data, lambda d: d["perturbations"][0].update(**{"from": []}))
        self.assertError(errors, "non-empty list")
        errors = self.errors_after(rel, data, lambda d: d["perturbations"][0].update(
            **{"from": [{"proposal": "P1", "row": "S1"}, {"proposal": "P1", "row": "S1"}]}))
        self.assertError(errors, "P1 row S1 is referenced 2 times")
        errors = self.errors_after(rel, data, lambda d: d["unmapped"][0].update(
            **{"from": [{"proposal": "P1", "row": "S2"}, {"source": "x", "row": "S2"}]}))
        self.assertError(errors, "from must be")

    def test_cli_draft_with_sources_only(self):
        self.add_source()
        code, out, err = run_cli("draft", "--purpose", "cli", "--source", f"smith2024:{SOURCE}",
                                 "--network", f"{NEKO}:{BNET}")
        self.assertEqual(code, 0, err)
        data = self.load("runs/orchestrator/cli/mapping.json")
        self.assertEqual((data["inputs"]["data"], data["inputs"]["sources"][0]["id"]), ([], "smith2024"))
        code, out, err = run_cli("draft", "--purpose", "cli2", "--network", f"{NEKO}:{BNET}")
        self.assertEqual(code, 1)
        self.assertIn("at least one", err)

    def test_criteria_declaration_cites_sources(self):
        rel, data = self.complete_sources()
        runs = []
        for n, (context, pert) in enumerate((("LUAD_EGFR", None), ("LUAD_EGFR", "S1"), ("LUAD_wt", None),
                                             ("LUAD_wt", "S1"))):
            traj = f"runs/boolean-dynamics-modeler/mb-1/exports/inv1/run{n}.csv"
            (self.root / traj).parent.mkdir(parents=True, exist_ok=True)
            (self.root / traj).write_text("Time,Proliferation\n0,0.5\n1,0.5\n", encoding="utf-8")
            runs.append({"context": context, "perturbation": pert, "trajectory": traj})
        self.save("runs/orchestrator/papers/runs.json", {"runs": runs})
        state.update(self.root, "record", {
            "id": "dec-map-src", "kind": "stage_approval", "stage": "data_mapping", "session_id": NEKO,
            "outputs": ["S1", "V1"], "artifact": {"path": rel, "sha256": sha(self.root / rel)},
            "approved_by": "researcher", "authorization": "researcher: ok"})
        result = mapping.criteria(self.root, rel, "runs/orchestrator/papers/runs.json", "dec-map-src")
        evidence = result["declarations"][0]["Required evidence"]
        short = sha(self.root / SOURCE)[:12]
        self.assertIn(f"source {SOURCE} sha256 {short} at Fig. 3C", evidence)
        self.assertIn(f"source {SOURCE} sha256 {short} at Table S2, EGFR row", evidence)


class StandaloneNetworkTests(MappingFixture):
    """B. A mapping onto a researcher-provided BNET with an explicit standalone approval."""

    def network(self, record_id="sa-1", rel=STANDALONE_BNET):
        return {"standalone_decision_id": record_id, "bnet": rel}

    def test_standalone_network_mapping_passes(self):
        self.add_standalone()
        rel, data = self.complete_sources(network=self.network())
        self.assertEqual(data["inputs"]["network"], {"standalone_decision_id": "sa-1", "bnet": STANDALONE_BNET,
                                                     "sha256": sha(self.root / STANDALONE_BNET)})
        self.assertEqual(mapping.check(self.root, rel), [])
        code, _, err = run_cli("draft", "--purpose", "sacli", "--source", f"smith2024:{SOURCE}",
                               "--standalone-network", f"sa-1:{STANDALONE_BNET}")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load("runs/orchestrator/sacli/mapping.json")["inputs"]["network"]["standalone_decision_id"],
                         "sa-1")

    def test_standalone_network_refusals(self):
        self.add_standalone()
        rel, data = self.complete_sources(network=self.network())
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["network"].update(sha256="0" * 64))
        self.assertError(errors, "inputs.network")
        other = self.add_standalone("sa-2", "inputs/models/other.bnet", BNET_TEXT + "KRAS, KRAS\n")
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["network"].update(standalone_decision_id="sa-2"))
        self.assertError(errors, "artifact")
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["network"].update(standalone_decision_id="sa-9"))
        self.assertError(errors, "sa-9")
        self.add_standalone("sa-stage", STANDALONE_BNET, kind="stage_approval", stage="topology")
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["network"].update(standalone_decision_id="sa-stage"))
        self.assertError(errors, "standalone_approval")
        self.add_standalone("sa-multi", STANDALONE_BNET, stage="multicellular")
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["network"].update(standalone_decision_id="sa-multi"))
        self.assertError(errors, "boolean-dynamics")
        bnd = "inputs/models/user.bnd"
        (self.root / bnd).write_text("Node A { logic = A; }\n", encoding="utf-8")
        self.add_standalone("sa-bnd", bnd)
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["network"].update(
            standalone_decision_id="sa-bnd", bnet=bnd, sha256=sha(self.root / bnd)))
        self.assertError(errors, ".bnet")
        errors = self.errors_after(rel, data, lambda d: d["inputs"]["network"].update(neko_session=NEKO))
        self.assertError(errors, "inputs.network must have exactly")
        del other


class RedraftTests(MappingFixture):
    """D. A NeKo re-export: draft --from copies the mapping onto the new BNET."""

    NEW_BNET = f"runs/network-curator/{NEKO}/exports/inv2/model.bnet"
    # EGFR removed, MAPK1 and Survival rules changed (MAPK1 is not used by the mapping).
    NEW_TEXT = "targets, factors\nMAPK1, MAPK1\nProliferation, MAPK1\nSurvival, !MAPK1\n"

    def setUp(self):
        super().setUp()
        self.rel, self.data = self.complete()
        new = self.root / self.NEW_BNET
        new.parent.mkdir(parents=True)
        new.write_text(self.NEW_TEXT, encoding="utf-8")

    def test_redraft_copies_and_notes(self):
        before = (self.root / self.rel).read_bytes()
        path, notes = mapping.redraft(self.root, self.rel, "luad2", (NEKO, self.NEW_BNET))
        new_rel = path.relative_to(self.root).as_posix()
        self.assertEqual(new_rel, "runs/orchestrator/luad2/mapping.json")
        self.assertEqual((self.root / self.rel).read_bytes(), before)
        new = self.load(new_rel)
        for key in ("contexts", "perturbations", "readouts", "criteria", "unmapped"):
            self.assertEqual(new[key], self.data[key], key)
        self.assertEqual(new["inputs"]["data"], self.data["inputs"]["data"])
        self.assertEqual(new["inputs"]["sources"], [])
        self.assertEqual(new["inputs"]["network"], {"neko_session": NEKO, "bnet": self.NEW_BNET,
                                                    "sha256": sha(self.root / self.NEW_BNET)})
        absent = [n for n in notes if "absent" in n]
        changed = [n for n in notes if "rediscuss" in n]
        self.assertEqual(len(absent), 1, notes)
        self.assertIn("EGFR", absent[0])
        self.assertEqual(len(changed), 1, notes)
        self.assertIn("Survival", changed[0])
        self.assertEqual(len(notes), 2, notes)
        errors = mapping.check(self.root, new_rel)
        self.assertEqual(sorted(e.split(":")[0] for e in errors), ["context LUAD_EGFR", "perturbation S1 model"], errors)
        self.assertTrue(all("EGFR" in e for e in errors), errors)
        with self.assertRaisesRegex(ValueError, "exists"):
            mapping.redraft(self.root, self.rel, "luad2", (NEKO, self.NEW_BNET))
        with self.assertRaisesRegex(ValueError, "exists"):
            mapping.redraft(self.root, self.rel, "luad", (NEKO, self.NEW_BNET))

    def test_redraft_cli(self):
        code, out, err = run_cli("draft", "--from", self.rel, "--purpose", "luad3", "--network", f"{NEKO}:{self.NEW_BNET}")
        self.assertEqual(code, 0, err)
        self.assertIn("note: node EGFR", out)
        self.assertIn("rediscuss", out)
        self.assertIn("runs/orchestrator/luad3/mapping.json", out)
        code, out, err = run_cli("draft", "--from", self.rel, "--purpose", "luad4", "--data", f"{self.sid}:P1:dec-data-1",
                                 "--network", f"{NEKO}:{self.NEW_BNET}")
        self.assertEqual(code, 1)
        self.assertIn("--from", err)
        code, out, err = run_cli("draft", "--from", self.rel, "--purpose", "luad3", "--network", f"{NEKO}:{self.NEW_BNET}")
        self.assertEqual(code, 1)
        self.assertIn("exists", err)


if __name__ == "__main__":
    unittest.main()

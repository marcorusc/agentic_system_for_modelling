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
                 "P3": ("seed_genes", "neko", SEEDS)}
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

    def test_criteria_scenario_contrast_input_order(self):
        result = mapping.criteria(self.root, self.rel, self.runs_rel)
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
        self.save("VALIDATION_CRITERIA.yaml", {"schema_version": 1, "criteria": result["criteria"]})
        report = evaluate(self.root, "VALIDATION_CRITERIA.yaml")
        self.assertEqual(report["results"][0]["status"], "passed", report)

    def test_criteria_missing_run_refused(self):
        runs = self.load(self.runs_rel)
        runs["runs"] = [r for r in runs["runs"] if (r["context"], r["perturbation"]) != ("LUAD_wt", None)]
        self.save(self.runs_rel, runs)
        with self.assertRaisesRegex(ValueError, "LUAD_wt"):
            mapping.criteria(self.root, self.rel, self.runs_rel)
        runs["runs"].append({"context": "LUAD_wt", "perturbation": None, "trajectory": "outside.csv"})
        (self.root / "outside.csv").write_text("Time,Proliferation\n0,0.5\n", encoding="utf-8")
        self.save(self.runs_rel, runs)
        with self.assertRaisesRegex(ValueError, "runs/boolean-dynamics-modeler"):
            mapping.criteria(self.root, self.rel, self.runs_rel)

    def test_merge_refuses_duplicate_id(self):
        entries = mapping.criteria(self.root, self.rel, self.runs_rel)["criteria"]
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
        entries = mapping.criteria(self.root, self.rel, self.runs_rel)["criteria"]
        mapping.merge_into(self.root, "VALIDATION_CRITERIA.yaml", entries)
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)

    def test_criteria_duplicate_trajectory_refused(self):
        runs = self.load(self.runs_rel)
        runs["runs"][3]["trajectory"] = runs["runs"][2]["trajectory"]
        self.save(self.runs_rel, runs)
        with self.assertRaisesRegex(ValueError, "same trajectory"):
            mapping.criteria(self.root, self.rel, self.runs_rel)

    def test_cli_exit_codes(self):
        def run(*argv):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = mapping.main(list(argv))
            return code, out.getvalue(), err.getvalue()
        code, out, err = run("check", self.rel)
        self.assertEqual(code, 0, err)
        code, out, err = run("criteria", self.rel, "--runs", self.runs_rel, "--merge-into", "VALIDATION_CRITERIA.yaml")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["criteria"][0]["criterion_id"], "V1")
        self.assertEqual(self.load("VALIDATION_CRITERIA.yaml")["criteria"][0]["criterion_id"], "V1")
        code, out, err = run("criteria", self.rel, "--runs", self.runs_rel, "--out", "runs/orchestrator/luad/criteria.json")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.load("runs/orchestrator/luad/criteria.json")["criteria"][0]["criterion_id"], "V1")
        code, out, err = run("criteria", self.rel, "--runs", self.runs_rel, "--merge-into", "VALIDATION_CRITERIA.yaml")
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


if __name__ == "__main__":
    unittest.main()

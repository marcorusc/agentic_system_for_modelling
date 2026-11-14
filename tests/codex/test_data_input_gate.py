"""DATA_INPUT dispatch checks: NeKo seeds and MaBoSS mappings consume only approved, hash-checked data."""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from scripts import gate, state
from scripts.data import mapping
from tests.data.test_mapping import (BNET, BNET_TEXT, NEKO, SOURCE, STANDALONE_BNET, STANDALONE_OUTPUTS,
                                     MappingFixture, run_cli, sha)

REFUSAL = "brief references data-analyst artifacts without a DATA_INPUT line; see CLAUDE.md"
HOOK = state.ROOT / ".claude" / "scripts" / "stage_gate_guard.py"
OUTPUTS = ["Proliferation", "Survival"]
STAGE_GATE = "STAGE_GATE " + json.dumps({"upstream_session_id": NEKO, "outputs": OUTPUTS})


class DataInputFixture(MappingFixture):
    SEEDS_REL = "runs/orchestrator/kras-seeds/seeds.json"

    def setUp(self):
        super().setUp()
        self.seeds = f"{self.base}/proposals/P3_seed_genes.csv"
        self.mapping_rel, self.mapping_data = self.complete()
        self.approve_mapping("dec-map-1", self.mapping_rel)
        for name in ("CURRENT_STATE.md", "VALIDATION_PLAN.md"):
            shutil.copyfile(state.ROOT / "templates" / name, self.root / name)

    def write_seeds(self, rel, symbols, cite=True):
        data = {"schema_version": 1,
                "sources": [{"id": "smith2024", "path": SOURCE, "sha256": sha(self.root / SOURCE)}],
                "seeds": [{"hgnc_symbol": s, "from": [{"source": "smith2024", "locator": "Table 1"}] if cite else []}
                          for s in symbols]}
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        self.save(rel, data)

    def approve_seeds(self, record_id, rel, outputs, stage="data_seeds", session_id="kras-seeds"):
        state.update(self.root, "record", {
            "id": record_id, "kind": "stage_approval", "stage": stage, "session_id": session_id,
            "outputs": outputs, "artifact": {"path": rel, "sha256": sha(self.root / rel)},
            "approved_by": "researcher", "authorization": "researcher: seeds ok"})

    def seeds_line(self, rel=None, digest=None, approval="dec-seeds-1", **extra):
        rel = rel or self.SEEDS_REL
        return "DATA_INPUT " + json.dumps({"seeds": rel, "sha256": digest or sha(self.root / rel),
                                           "approval": approval, **extra})

    def seeds_task(self, **kw):
        return f"{self.seeds_line(**kw)}\nBuild the network from the seeds file named above; the source is {SOURCE}."

    def approve_mapping(self, record_id, rel, outputs=("S1", "V1")):
        state.update(self.root, "record", {
            "id": record_id, "kind": "stage_approval", "stage": "data_mapping", "session_id": NEKO,
            "outputs": list(outputs), "artifact": {"path": rel, "sha256": sha(self.root / rel)},
            "approved_by": "researcher", "authorization": "researcher: mapping ok"})

    def neko_line(self, proposals=None, session=None):
        proposals = {"P3": sha(self.root / self.seeds)} if proposals is None else proposals
        return "DATA_INPUT " + json.dumps({"data_session": session or self.sid, "proposals": proposals})

    def neko_task(self, **kw):
        return f"{self.neko_line(**kw)}\nBuild the network from the seed file {self.seeds} (hgnc_symbol column)."

    def maboss_line(self, rel=None, digest=None, approval="dec-map-1"):
        rel = rel or self.mapping_rel
        return "DATA_INPUT " + json.dumps({"mapping": rel, "sha256": digest or sha(self.root / rel), "approval": approval})

    def maboss_task(self, gate_line=STAGE_GATE, **kw):
        return f"{gate_line}\n{self.maboss_line(**kw)}\nSimulate exactly the mapping's scenarios."

    def stage_gate_ready(self):
        """Make the NeKo session an exported, reviewed, approved upstream so check_task passes."""
        bnet = self.root / BNET
        manifest = {"source": {"server": "NeKo", "session_id": NEKO}, "schema_name": "mcp-biomodelling-handoff",
                    "schema_version": "1.0", "handoff_type": "neko-to-maboss",
                    "network": {"nodes": ["EGFR", "MAPK1", "Proliferation", "Survival"], "output_nodes": OUTPUTS},
                    "bnet_file": {"path": BNET, "server": "NeKo", "session_id": NEKO, "role": "neko_bnet",
                                  "name": bnet.name, "suffix": ".bnet", "media_type": "text/plain",
                                  "size_bytes": bnet.stat().st_size, "sha256": sha(bnet)}}
        handoff = self.root / "runs" / "network-curator" / NEKO / "handoff.json"
        handoff.write_text(json.dumps(manifest), encoding="utf-8")
        ref = {"path": f"runs/network-curator/{NEKO}/handoff.json", "sha256": sha(handoff)}
        state.update(self.root, "registry-add", dict(zip(state.REGISTRY, [
            "network-curator", NEKO, "topology", "active", "—", "pending", ref["path"]])))
        review = {"id": "review-neko", "kind": "stage_review", "session_id": NEKO, "stage": "topology",
                  "outcome": "approved", "artifact": ref}
        for role in ("scientific-reviewer", "reproducibility-auditor"):
            report = self.root / "runs" / f"{role}.md"
            report.write_text("independent bounded review", encoding="utf-8")
            review[role] = {"path": f"runs/{role}.md", "sha256": sha(report)}
        state.update(self.root, "record", review)
        state.update(self.root, "record", {
            "id": "approval-neko", "kind": "stage_approval", "session_id": NEKO, "stage": "topology",
            "downstream_stage": "boolean-dynamics", "outputs": OUTPUTS, "approved_by": "researcher",
            "authorization": "researcher approved this revision and outputs", "artifact": ref})
        state.update(self.root, "registry-handoff", {"session_id": NEKO, "handoff": "approved"})
        state.update(self.root, "registry-handoff", {"session_id": NEKO, "handoff": "exported", "artifact": ref})

    def hook(self, subagent_type, prompt):
        event = {"tool_name": "Agent", "tool_input": {"subagent_type": subagent_type, "prompt": prompt}}
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root), "PYTHONPATH": str(state.ROOT)}
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), text=True,
                              capture_output=True, env=env, timeout=60)


class NekoDataInputTests(DataInputFixture):
    def test_neko_data_input_ok(self):
        result = gate.check_data_input(self.root, "network_curator", self.neko_task())
        self.assertEqual(result["data_session"], self.sid)
        self.assertEqual(result["approval_id"], "dec-data-1")
        self.assertEqual(result["proposals"], {"P3": {"path": self.seeds, "sha256": sha(self.root / self.seeds)}})

    def restrict_first_approval(self, outputs):
        decisions = self.root / "DECISIONS.md"
        text = decisions.read_text(encoding="utf-8")
        pattern = r'"outputs": \[\s*"P1",\s*"P2",\s*"P3"\s*\]'
        self.assertRegex(text, pattern)
        decisions.write_text(re.sub(pattern, f'"outputs": {json.dumps(outputs)}', text, count=1), encoding="utf-8")

    def test_neko_approvals_are_cumulative(self):
        # P3 approved in record A and P4 in a later record B: both usable in one DATA_INPUT.
        self.approve("dec-data-2", ["P4"])
        seeds4 = f"{self.base}/proposals/P4_seed_genes.csv"
        proposals = {"P3": sha(self.root / self.seeds), "P4": sha(self.root / seeds4)}
        result = gate.check_data_input(self.root, "network_curator", self.neko_task(proposals=proposals))
        self.assertEqual(set(result["proposals"]), {"P3", "P4"})
        # A later partial approval does not revoke earlier ones.
        self.approve("dec-data-3", ["P1"])
        self.assertEqual(set(gate.check_data_input(self.root, "network_curator",
                                                   self.neko_task(proposals=proposals))["proposals"]), {"P3", "P4"})

    def test_neko_wrong_hash_refused(self):
        with self.assertRaisesRegex(ValueError, "sha256"):
            gate.check_data_input(self.root, "network_curator", self.neko_task(proposals={"P3": "0" * 64}))
        for bad in ({}, {"P3": "abc"}, {"P3": 7}, ["P3"]):
            with self.assertRaises(ValueError):
                gate.check_data_input(self.root, "network_curator", self.neko_task(proposals=bad))
        # The seed file changed on disk after approval: no longer the approved handoff artifact.
        line = self.neko_line()
        (self.root / self.seeds).write_text("hgnc_symbol,tier,evidence\nKRAS,core,lit\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "approved handoff"):
            gate.check_data_input(self.root, "network_curator", line)

    def test_neko_unapproved_proposal_refused(self):
        with self.assertRaisesRegex(ValueError, "P9"):
            gate.check_data_input(self.root, "network_curator", self.neko_task(proposals={"P9": "0" * 64}))
        with self.assertRaisesRegex(ValueError, "no researcher stage_approval"):
            gate.check_data_input(self.root, "network_curator", self.neko_task(session="data-other-session"))
        # P3 listed only in a record that binds a stale handoff sha is refused.
        self.restrict_first_approval(["P1"])
        handoff = self.root / self.base / "handoff.json"
        original = handoff.read_text(encoding="utf-8")
        handoff.write_text(original + " ", encoding="utf-8")
        self.approve("dec-data-stale", ["P3"])
        handoff.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not in the approved outputs"):
            gate.check_data_input(self.root, "network_curator", self.neko_task())
        # P3 never listed at all.
        self.approve("dec-data-2", ["P1", "P2"])
        with self.assertRaisesRegex(ValueError, "not in the approved outputs"):
            gate.check_data_input(self.root, "network_curator", self.neko_task())
        # A handoff changed after approval invalidates the approval.
        handoff = self.root / self.base / "handoff.json"
        handoff.write_text(handoff.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed since approval"):
            gate.check_data_input(self.root, "network_curator", self.neko_task())

    def test_neko_wrong_kind_or_layer_refused(self):
        p1 = f"{self.base}/proposals/P1_perturbations.csv"
        with self.assertRaisesRegex(ValueError, "seed_genes"):
            gate.check_data_input(self.root, "network_curator",
                                  self.neko_task(proposals={"P1": sha(self.root / p1)}))
        entry = {"id": "P3", "kind": "seed_genes", "target_layer": "maboss", "path": self.seeds,
                 "sha256": sha(self.root / self.seeds)}
        with mock.patch.object(gate.approvals, "require_proposal_approved", return_value=entry):
            with self.assertRaisesRegex(ValueError, "neko"):
                gate.check_data_input(self.root, "network_curator", self.neko_task())

    def test_neko_handoff_must_validate_now(self):
        with mock.patch("scripts.codex.validate_handoff.validate_handoff", side_effect=ValueError("broken")):
            with self.assertRaisesRegex(ValueError, "no longer validates"):
                gate.check_data_input(self.root, "network_curator", self.neko_task())

    def test_neko_malformed_line_refused(self):
        for line in ("DATA_INPUT [1]", "DATA_INPUT {", 'DATA_INPUT {"data_session": "x"}',
                     "DATA_INPUT " + json.dumps({"data_session": self.sid, "proposals": {}, "extra": 1})):
            with self.assertRaises(ValueError):
                gate.check_data_input(self.root, "network_curator", line)
        # Line 1 only, never repeated or elsewhere.
        with self.assertRaisesRegex(ValueError, "line 1"):
            gate.check_data_input(self.root, "network_curator", "Build a network.\n" + self.neko_line())
        with self.assertRaisesRegex(ValueError, "line 1"):
            gate.check_data_input(self.root, "network_curator", self.neko_line() + "\n" + self.neko_line())

    def test_neko_data_path_of_other_session_refused(self):
        task = self.neko_task() + "\nAlso read runs/data-analyst/data-other-session/proposals/P1.csv."
        with self.assertRaisesRegex(ValueError, "data-other-session"):
            gate.check_data_input(self.root, "network_curator", task)


class MabossDataInputTests(DataInputFixture):
    def setUp(self):
        super().setUp()
        self.stage_gate_ready()

    def test_maboss_mapping_ok(self):
        result = gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task())
        self.assertEqual(result, {"mapping": self.mapping_rel, "sha256": sha(self.root / self.mapping_rel),
                                  "approval_id": "dec-map-1", "neko_session": NEKO})
        # The mapping's own data paths may be named in the brief.
        task = self.maboss_task() + f"\nInputs: {self.base}/proposals/P1_perturbations.csv"
        self.assertEqual(gate.check_data_input(self.root, "boolean_dynamics_modeler", task)["approval_id"], "dec-map-1")

    def test_maboss_unapproved_mapping_refused(self):
        with self.assertRaisesRegex(ValueError, "data_mapping"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task(approval="dec-data-1"))
        with self.assertRaisesRegex(ValueError, "not found"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task(approval="nope"))
        with self.assertRaisesRegex(ValueError, "sha256"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task(digest="0" * 64))
        other, _ = self.complete("other")
        with self.assertRaisesRegex(ValueError, "artifact must be"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task(rel=other))
        # Changed after approval.
        task = self.maboss_task()
        data = dict(self.mapping_data, unmapped=self.mapping_data["unmapped"][:1])
        self.save(self.mapping_rel, data)
        with self.assertRaisesRegex(ValueError, "changed since approval"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", task)
        for bad in ('DATA_INPUT {"mapping": "x"}', "DATA_INPUT []", "DATA_INPUT " + json.dumps(
                {"mapping": self.mapping_rel, "sha256": "0" * 64, "approval": "dec-map-1", "x": 1})):
            with self.assertRaises(ValueError):
                gate.check_data_input(self.root, "boolean_dynamics_modeler", f"{STAGE_GATE}\n{bad}")

    def test_maboss_mapping_failing_check_refused(self):
        draft = self.draft("todo")  # approved as drafted: unmapped reasons are still TODO
        self.approve_mapping("dec-map-todo", draft)
        with self.assertRaisesRegex(ValueError, "TODO"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler",
                                  self.maboss_task(rel=draft, approval="dec-map-todo"))
        # The mapping is unchanged but its network changed since: check fails at dispatch time.
        task = self.maboss_task()
        (self.root / BNET).write_text(BNET_TEXT + "Extra, EGFR\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "mapping check failed"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", task)

    def test_maboss_approval_outputs_must_equal_mapping_ids(self):
        for record_id, outputs in (("dec-map-zzz", ["ZZZ"]), ("dec-map-s1", ["S1"]),
                                   ("dec-map-extra", ["S1", "V1", "V2"])):
            self.approve_mapping(record_id, self.mapping_rel, outputs)
            with self.assertRaisesRegex(ValueError, "outputs"):
                gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task(approval=record_id))
        self.approve_mapping("dec-map-reordered", self.mapping_rel, ["V1", "S1"])
        self.assertEqual(gate.check_data_input(self.root, "boolean_dynamics_modeler",
                                               self.maboss_task(approval="dec-map-reordered"))["approval_id"],
                         "dec-map-reordered")

    def test_maboss_network_mismatch_with_stage_gate_refused(self):
        other = "STAGE_GATE " + json.dumps({"upstream_session_id": "neko-session-2", "outputs": OUTPUTS})
        with self.assertRaisesRegex(ValueError, "neko-session-2"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task(gate_line=other))
        standalone = "STAGE_GATE " + json.dumps({"standalone_decision_id": "sa-1", "outputs": OUTPUTS})
        with self.assertRaisesRegex(ValueError, "upstream_session_id"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task(gate_line=standalone))
        with self.assertRaisesRegex(ValueError, "line 2"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_line())


    def test_maboss_mapping_bnet_must_be_the_approved_one(self):
        other = self.root / f"runs/network-curator/{NEKO}/exports/inv2/draft.bnet"
        other.parent.mkdir(parents=True)
        other.write_text(BNET_TEXT + "KRAS, KRAS\n", encoding="utf-8")
        rel = self.draft("other")
        data = self.load(rel)
        data["inputs"]["network"] = {"neko_session": NEKO, "bnet": other.relative_to(self.root).as_posix(),
                                     "sha256": sha(other)}
        data["contexts"] = {"LUAD_EGFR": [{"node": "KRAS", "state": 1}], "LUAD_wt": []}
        for key in ("perturbations", "readouts", "criteria", "unmapped"):
            data[key] = self.mapping_data[key]
        self.save(rel, data)
        self.assertEqual(mapping.check(self.root, rel), [])
        self.approve_mapping("dec-map-2", rel)
        task = self.maboss_task(rel=rel, approval="dec-map-2")
        with self.assertRaisesRegex(ValueError, "not the BNET of the approved NeKo handoff"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", task)
        self.assertEqual(self.hook("boolean-dynamics-modeler", task).returncode, 2)
        self.assertEqual(gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task())["approval_id"],
                         "dec-map-1")

    def test_maboss_approval_session_must_be_the_neko_session(self):
        state.update(self.root, "record", {
            "id": "dec-map-bad", "kind": "stage_approval", "stage": "data_mapping", "session_id": "neko-session-2",
            "outputs": ["S1", "V1"], "artifact": {"path": self.mapping_rel, "sha256": sha(self.root / self.mapping_rel)},
            "approved_by": "researcher", "authorization": "researcher: mapping ok"})
        with self.assertRaisesRegex(ValueError, "session_id"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task(approval="dec-map-bad"))


class ScopeTests(DataInputFixture):
    def test_data_path_without_data_input_refused(self):
        prose = f"see {self.seeds} for the seeds"
        for specialist, task in (("network_curator", f"Build a network.\n{prose}"),
                                 ("network_curator", prose),
                                 ("boolean_dynamics_modeler", f"{STAGE_GATE}\nSimulate; {prose}")):
            with self.assertRaises(ValueError) as caught:
                gate.check_data_input(self.root, specialist, task)
            self.assertEqual(str(caught.exception), REFUSAL)

    def test_noncanonical_data_input_refused(self):
        line = self.maboss_line(digest="0" * 64)
        body = line[len("DATA_INPUT"):]
        variants = [f"`{line}`", f"> {line}", f"\ufeff{line}", f" {line}", "data_input" + body, "DATA-INPUT" + body,
                    "DATAINPUT" + body, "Data_Input" + body, "DATA\u200b_INPUT" + body, "DATA\uff3fINPUT" + body]
        for variant in variants:
            with self.assertRaises(ValueError, msg=repr(variant)):
                gate.check_data_input(self.root, "boolean_dynamics_modeler", f"{STAGE_GATE}\n{variant}\nSimulate.")
            with self.assertRaises(ValueError, msg=repr(variant)):
                gate.check_data_input(self.root, "network_curator", f"Build.\n{variant}")
        # The canonical line plus any other mention is refused too.
        for extra in ("Follow the DATA_INPUT line above.", "see `data_input`", "DATA-INPUT"):
            with self.assertRaises(ValueError, msg=extra):
                gate.check_data_input(self.root, "boolean_dynamics_modeler", f"{self.maboss_task()}\n{extra}")
            with self.assertRaises(ValueError, msg=extra):
                gate.check_data_input(self.root, "network_curator", f"{self.neko_task()}\n{extra}")
        # Ordinary prose "data input" (with a space) is not a DATA_INPUT spelling.
        self.assertIsNone(gate.check_data_input(self.root, "network_curator", "No data input is used."))

    def test_data_session_id_or_bare_dir_without_data_input_refused(self):
        for specialist, prefix in (("network_curator", "Build.\n"), ("boolean_dynamics_modeler", f"{STAGE_GATE}\n")):
            for prose in (f"seeds come from data session {self.sid}", "outputs live in runs/data-analyst",
                          "see runs\\data-analyst\\x", "see RUNS/Data-Analyst/x", "data-20990101T000000Z-deadbeef"):
                with self.assertRaises(ValueError, msg=prose) as caught:
                    gate.check_data_input(self.root, specialist, prefix + prose)
                self.assertEqual(str(caught.exception), REFUSAL)
        # With a DATA_INPUT line, another data session id is out of scope.
        with self.assertRaisesRegex(ValueError, "data-20990101T000000Z-deadbeef"):
            gate.check_data_input(self.root, "network_curator",
                                  self.neko_task() + "\nalso data-20990101T000000Z-deadbeef")

    def test_other_specialists_unaffected(self):
        task = f"Review the evidence; see {self.seeds}.\nDATA_INPUT not-json"
        for specialist in ("literature_reviewer", "multicellular_configurator", "ode_modeler", "data_analyst",
                           "scientific_reviewer", "reproducibility_auditor"):
            self.assertIsNone(gate.check_data_input(self.root, specialist, task))
        result = self.hook("literature-reviewer", task)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_data_unchanged(self):
        for specialist, task in (("network_curator", "Build a network from EGFR, KRAS.\nNo BNET/handoff export."),
                                 ("network_curator", ""),
                                 ("boolean_dynamics_modeler", f"{STAGE_GATE}\nImport and simulate.")):
            self.assertIsNone(gate.check_data_input(self.root, specialist, task))
        result = self.hook("network-curator", "Build a network from EGFR, KRAS.")
        self.assertEqual(result.returncode, 0, result.stderr)


class HookTests(DataInputFixture):
    def test_hook_neko_allow_and_deny(self):
        result = self.hook("network-curator", self.neko_task())
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.hook("network-curator", f"Build a network from {self.seeds}.")
        self.assertEqual(result.returncode, 2)
        self.assertIn(REFUSAL, result.stderr)
        result = self.hook("plugin:network-curator", self.neko_task(proposals={"P3": "0" * 64}))
        self.assertEqual(result.returncode, 2)
        self.assertIn("sha256", result.stderr)
        for prompt in (["DATA_INPUT"], 7, "DATA_INPUT " + "[" * 100000):
            result = self.hook("network-curator", prompt)
            self.assertEqual(result.returncode, 2, result.stderr)

    def test_hook_fails_closed_on_malformed_prompts(self):
        deep = {"boolean-dynamics-modeler": "STAGE_GATE " + "[" * 100000,
                "multicellular-configurator": "STAGE_GATE " + "[" * 100000,
                "network-curator": "DATA_INPUT " + "[" * 100000}
        for role in deep:
            for prompt in (7, ["x"], {"a": 1}, True, deep[role]):
                result = self.hook(role, prompt)
                self.assertEqual(result.returncode, 2, (role, repr(prompt)[:40], result.stderr[-300:]))
                self.assertIn("blocked", result.stderr)
        self.assertEqual(self.hook("network-curator", None).returncode, 0)

    def test_hook_maboss_allow_and_deny(self):
        # STAGE_GATE is checked first: with no exported upstream, the DATA_INPUT line cannot help.
        result = self.hook("boolean-dynamics-modeler", self.maboss_task())
        self.assertEqual(result.returncode, 2)
        self.assertIn("registry", result.stderr)
        self.stage_gate_ready()
        result = self.hook("boolean-dynamics-modeler", self.maboss_task())
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.hook("boolean-dynamics-modeler", f"{STAGE_GATE}\nSimulate; seeds at {self.seeds}.")
        self.assertEqual(result.returncode, 2)
        self.assertIn(REFUSAL, result.stderr)
        result = self.hook("boolean-dynamics-modeler", self.maboss_task(approval="dec-data-1"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("data_mapping", result.stderr)


REDRAFT = "redraft with mapping.py draft --from"
SA_GATE = "STAGE_GATE " + json.dumps({"standalone_decision_id": "sa-1", "outputs": STANDALONE_OUTPUTS})


class StandaloneNetworkGateTests(DataInputFixture):
    """B. MaBoSS DATA_INPUT after a standalone STAGE_GATE: the mapping must target that BNET."""

    def setUp(self):
        super().setUp()
        self.add_standalone()
        self.sa_rel, self.sa_data = self.complete_sources(
            "sa", network={"standalone_decision_id": "sa-1", "bnet": STANDALONE_BNET})
        self.approve_sa_mapping("dec-map-sa", self.sa_rel)

    def approve_sa_mapping(self, record_id, rel, session_id="sa-1"):
        state.update(self.root, "record", {
            "id": record_id, "kind": "stage_approval", "stage": "data_mapping", "session_id": session_id,
            "outputs": ["S1", "V1"], "artifact": {"path": rel, "sha256": sha(self.root / rel)},
            "approved_by": "researcher", "authorization": "researcher: mapping ok"})

    def sa_task(self, gate_line=SA_GATE, rel=None, approval="dec-map-sa"):
        return self.maboss_task(gate_line=gate_line, rel=rel or self.sa_rel, approval=approval)

    def test_standalone_mapping_accepted_by_check_and_hook(self):
        result = gate.check_data_input(self.root, "boolean_dynamics_modeler", self.sa_task())
        self.assertEqual(result, {"mapping": self.sa_rel, "sha256": sha(self.root / self.sa_rel),
                                  "approval_id": "dec-map-sa", "standalone_decision_id": "sa-1"})
        hook = self.hook("boolean-dynamics-modeler", self.sa_task())
        self.assertEqual(hook.returncode, 0, hook.stderr)
        self.assertEqual(mapping.check(self.root, self.sa_rel, stage_gate=SA_GATE), [])

    def test_standalone_mismatched_sha_refused(self):
        # The standalone BNET changed after its authorization: the record and the mapping no longer bind.
        task = self.sa_task()
        (self.root / STANDALONE_BNET).write_text(BNET_TEXT + "# edited\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", task)
        self.assertEqual(self.hook("boolean-dynamics-modeler", task).returncode, 2)

    def test_standalone_different_id_refused(self):
        self.add_standalone("sa-2", "inputs/models/other.bnet", BNET_TEXT + "KRAS, KRAS\n")
        other = "STAGE_GATE " + json.dumps({"standalone_decision_id": "sa-2", "outputs": STANDALONE_OUTPUTS})
        with self.assertRaisesRegex(ValueError, "sa-2") as caught:
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.sa_task(gate_line=other))
        self.assertTrue(str(caught.exception).endswith(
            "check the STAGE_GATE record, or, if the network was re-authorized, redraft with mapping.py draft --from"),
            str(caught.exception))
        self.assertEqual(self.hook("boolean-dynamics-modeler", self.sa_task(gate_line=other)).returncode, 2)
        self.assertError(mapping.check(self.root, self.sa_rel, stage_gate=other), "sa-2")
        # The approval's session_id must be the standalone decision id.
        self.approve_sa_mapping("dec-map-sa-bad", self.sa_rel, session_id="sa-2")
        with self.assertRaisesRegex(ValueError, "session_id"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.sa_task(approval="dec-map-sa-bad"))

    def test_standalone_wrong_record_kind_refused(self):
        self.add_standalone("sa-stage", STANDALONE_BNET, kind="stage_approval", stage="boolean-dynamics")
        wrong = "STAGE_GATE " + json.dumps({"standalone_decision_id": "sa-stage", "outputs": STANDALONE_OUTPUTS})
        with self.assertRaises(ValueError):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.sa_task(gate_line=wrong))
        self.assertEqual(self.hook("boolean-dynamics-modeler", self.sa_task(gate_line=wrong)).returncode, 2)

    def test_standalone_mapping_with_neko_gate_refused(self):
        self.stage_gate_ready()
        with self.assertRaisesRegex(ValueError, "standalone_decision_id"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.sa_task(gate_line=STAGE_GATE))
        # The NeKo-upstream route is unchanged.
        self.assertEqual(gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task())["approval_id"],
                         "dec-map-1")


class SeedsGateTests(DataInputFixture):
    """C. NeKo DATA_INPUT naming an approved seeds.json built from researcher sources."""

    def setUp(self):
        super().setUp()
        self.add_source()
        self.write_seeds(self.SEEDS_REL, ["KRAS", "EGFR"])
        self.approve_seeds("dec-seeds-1", self.SEEDS_REL, ["EGFR", "KRAS"])

    def test_seeds_form_accepted_through_hook(self):
        result = gate.check_data_input(self.root, "network_curator", self.seeds_task())
        self.assertEqual(result, {"seeds": self.SEEDS_REL, "sha256": sha(self.root / self.SEEDS_REL),
                                  "approval_id": "dec-seeds-1", "symbols": ["KRAS", "EGFR"]})
        hook = self.hook("network-curator", self.seeds_task())
        self.assertEqual(hook.returncode, 0, hook.stderr)

    def test_seeds_wrong_sha_refused(self):
        with self.assertRaisesRegex(ValueError, "sha256"):
            gate.check_data_input(self.root, "network_curator", self.seeds_task(digest="0" * 64))
        for bad in ("abc", 7, "A" * 64):
            with self.assertRaises(ValueError):
                gate.check_data_input(self.root, "network_curator", self.seeds_task(digest=bad))
        task = self.seeds_task()
        self.write_seeds(self.SEEDS_REL, ["KRAS", "EGFR", "BRAF"])
        with self.assertRaisesRegex(ValueError, "sha256"):
            gate.check_data_input(self.root, "network_curator", task)
        result = self.hook("network-curator", task)
        self.assertEqual(result.returncode, 2)

    def test_seeds_wrong_stage_refused(self):
        self.approve_seeds("dec-seeds-map", self.SEEDS_REL, ["EGFR", "KRAS"], stage="data_mapping")
        with self.assertRaisesRegex(ValueError, "data_seeds"):
            gate.check_data_input(self.root, "network_curator", self.seeds_task(approval="dec-seeds-map"))
        with self.assertRaisesRegex(ValueError, "data_seeds"):
            gate.check_data_input(self.root, "network_curator", self.seeds_task(approval="dec-data-1"))
        with self.assertRaisesRegex(ValueError, "not found"):
            gate.check_data_input(self.root, "network_curator", self.seeds_task(approval="nope"))

    def test_seeds_outputs_must_equal_symbols(self):
        for record_id, outputs in (("dec-seeds-less", ["KRAS"]), ("dec-seeds-more", ["KRAS", "EGFR", "BRAF"])):
            self.approve_seeds(record_id, self.SEEDS_REL, outputs)
            with self.assertRaisesRegex(ValueError, "outputs"):
                gate.check_data_input(self.root, "network_curator", self.seeds_task(approval=record_id))

    def test_seeds_session_id_must_be_purpose(self):
        self.approve_seeds("dec-seeds-p", self.SEEDS_REL, ["EGFR", "KRAS"], session_id="other-purpose")
        with self.assertRaisesRegex(ValueError, "session_id"):
            gate.check_data_input(self.root, "network_curator", self.seeds_task(approval="dec-seeds-p"))

    def test_seeds_failing_check_refused(self):
        rel = "runs/orchestrator/uncited/seeds.json"
        self.write_seeds(rel, ["KRAS"], cite=False)
        self.approve_seeds("dec-seeds-bad", rel, ["KRAS"], session_id="uncited")
        with self.assertRaisesRegex(ValueError, "seeds check failed"):
            gate.check_data_input(self.root, "network_curator", self.seeds_task(rel=rel, approval="dec-seeds-bad"))
        with self.assertRaisesRegex(ValueError, "runs/orchestrator"):
            gate.check_data_input(self.root, "network_curator", self.seeds_task(rel=SOURCE, approval="dec-seeds-1"))

    def test_both_forms_or_mixed_keys_refused(self):
        both = self.seeds_line(data_session=self.sid, proposals={"P3": sha(self.root / self.seeds)})
        mixed = "DATA_INPUT " + json.dumps({"seeds": self.SEEDS_REL, "sha256": sha(self.root / self.SEEDS_REL),
                                            "proposals": {"P3": sha(self.root / self.seeds)}})
        partial = "DATA_INPUT " + json.dumps({"seeds": self.SEEDS_REL, "approval": "dec-seeds-1"})
        for line in (both, mixed, partial, f"{self.seeds_line()}\n{self.neko_line()}"):
            with self.assertRaisesRegex(ValueError, "DATA_INPUT", msg=line):
                gate.check_data_input(self.root, "network_curator", line)
            self.assertEqual(self.hook("network-curator", line).returncode, 2)

    def test_seeds_form_scope_refuses_data_sessions(self):
        task = self.seeds_task() + f"\nAlso see {self.seeds}."
        with self.assertRaisesRegex(ValueError, "outside its DATA_INPUT"):
            gate.check_data_input(self.root, "network_curator", task)

    def test_seeds_stage_is_a_governance_stage(self):
        self.assertIn("data_seeds", state.GOVERNANCE_STAGES)


class StaleMappingTests(DataInputFixture):
    """D. A NeKo re-export makes the approved mapping stale; check and gate say how to recover."""

    NEW_BNET = f"runs/network-curator/{NEKO}/exports/inv2/model.bnet"

    def setUp(self):
        super().setUp()
        self.stage_gate_ready()

    def reexport(self, text=BNET_TEXT + "# re-exported\n"):
        """A new approved NeKo handoff of the same session whose BNET differs."""
        bnet = self.root / self.NEW_BNET
        bnet.parent.mkdir(parents=True)
        bnet.write_text(text, encoding="utf-8")
        handoff = self.root / "runs" / "network-curator" / NEKO / "handoff.json"
        manifest = json.loads(handoff.read_text(encoding="utf-8"))
        manifest["bnet_file"].update(path=self.NEW_BNET, size_bytes=bnet.stat().st_size, sha256=sha(bnet))
        second = handoff.with_name("handoff-2.json")
        second.write_text(json.dumps(manifest), encoding="utf-8")
        ref = {"path": f"runs/network-curator/{NEKO}/handoff-2.json", "sha256": sha(second)}
        review = {"id": "review-neko-2", "kind": "stage_review", "session_id": NEKO, "stage": "topology",
                  "outcome": "approved", "artifact": ref}
        for role in ("scientific-reviewer", "reproducibility-auditor"):
            review[role] = {"path": f"runs/{role}.md", "sha256": sha(self.root / "runs" / f"{role}.md")}
        state.update(self.root, "record", review)
        state.update(self.root, "record", {
            "id": "approval-neko-2", "kind": "stage_approval", "session_id": NEKO, "stage": "topology",
            "downstream_stage": "boolean-dynamics", "outputs": OUTPUTS, "approved_by": "researcher",
            "authorization": "researcher approved the re-export", "artifact": ref})

    def test_check_with_stage_gate(self):
        self.assertEqual(mapping.check(self.root, self.mapping_rel, stage_gate=STAGE_GATE), [])
        self.assertEqual(mapping.check(self.root, self.mapping_rel,
                                       stage_gate=STAGE_GATE[len("STAGE_GATE "):]), [])
        self.reexport()
        errors = mapping.check(self.root, self.mapping_rel, stage_gate=STAGE_GATE)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("not the BNET of the approved NeKo handoff", errors[0])
        self.assertTrue(errors[0].endswith(REDRAFT), errors)
        self.assertEqual(mapping.check(self.root, self.mapping_rel), [])  # without --stage-gate: not detectable
        code, out, err = run_cli("check", self.mapping_rel, "--stage-gate", STAGE_GATE[len("STAGE_GATE "):])
        self.assertEqual(code, 1)
        self.assertIn(REDRAFT, err)
        bad = mapping.check(self.root, self.mapping_rel, stage_gate="{not json")
        self.assertEqual(len(bad), 1)
        self.assertIn("STAGE_GATE", bad[0])

    def test_gate_refusal_carries_hint_and_redraft_recovers(self):
        self.reexport()
        with self.assertRaises(ValueError) as caught:
            gate.check_data_input(self.root, "boolean_dynamics_modeler", self.maboss_task())
        self.assertIn("not the BNET of the approved NeKo handoff", str(caught.exception))
        self.assertTrue(str(caught.exception).endswith(REDRAFT), str(caught.exception))
        result = self.hook("boolean-dynamics-modeler", self.maboss_task())
        self.assertEqual(result.returncode, 2)
        self.assertIn(REDRAFT, result.stderr)
        path, notes = mapping.redraft(self.root, self.mapping_rel, "luad-r2", (NEKO, self.NEW_BNET))
        self.assertEqual(notes, [])
        new_rel = path.relative_to(self.root).as_posix()
        self.assertEqual(mapping.check(self.root, new_rel, stage_gate=STAGE_GATE), [])
        self.approve_mapping("dec-map-r2", new_rel)
        task = self.maboss_task(rel=new_rel, approval="dec-map-r2")
        self.assertEqual(gate.check_data_input(self.root, "boolean_dynamics_modeler", task)["approval_id"], "dec-map-r2")
        self.assertEqual(self.hook("boolean-dynamics-modeler", task).returncode, 0)


class ReadoutOutputsTests(DataInputFixture):
    """A mapping may read only nodes the STAGE_GATE approved as MaBoSS outputs."""

    def widen(self, rel, data, record_id, approve):
        data = json.loads(json.dumps(data))
        data["readouts"][0]["nodes"].append("MAPK1")  # a BNET node, not an approved output
        self.save(rel, data)
        self.assertEqual(mapping.check(self.root, rel), [])  # valid on its own
        approve(record_id, rel)

    def test_neko_route_readout_outside_outputs_refused(self):
        self.stage_gate_ready()
        self.widen(self.mapping_rel, self.mapping_data, "dec-map-wide", self.approve_mapping)
        task = self.maboss_task(approval="dec-map-wide")
        with self.assertRaisesRegex(ValueError, r"MAPK1.*STAGE_GATE outputs") as caught:
            gate.check_data_input(self.root, "boolean_dynamics_modeler", task)
        self.assertNotIn("Proliferation,", str(caught.exception).split("STAGE_GATE outputs")[0])
        result = self.hook("boolean-dynamics-modeler", task)
        self.assertEqual(result.returncode, 2)
        self.assertIn("MAPK1", result.stderr)
        errors = mapping.check(self.root, self.mapping_rel, stage_gate=STAGE_GATE)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn(str(caught.exception), errors[0])
        code, _, err = run_cli("check", self.mapping_rel, "--stage-gate", STAGE_GATE[len("STAGE_GATE "):])
        self.assertEqual(code, 1)
        self.assertIn("MAPK1", err)

    def test_standalone_route_readout_outside_outputs_refused(self):
        self.add_standalone()
        rel, data = self.complete_sources("sa", network={"standalone_decision_id": "sa-1", "bnet": STANDALONE_BNET})

        def approve(record_id, path):
            state.update(self.root, "record", {
                "id": record_id, "kind": "stage_approval", "stage": "data_mapping", "session_id": "sa-1",
                "outputs": ["S1", "V1"], "artifact": {"path": path, "sha256": sha(self.root / path)},
                "approved_by": "researcher", "authorization": "researcher: mapping ok"})
        self.widen(rel, data, "dec-map-sa-wide", approve)
        task = self.maboss_task(gate_line=SA_GATE, rel=rel, approval="dec-map-sa-wide")
        with self.assertRaisesRegex(ValueError, r"MAPK1.*STAGE_GATE outputs"):
            gate.check_data_input(self.root, "boolean_dynamics_modeler", task)
        self.assertEqual(self.hook("boolean-dynamics-modeler", task).returncode, 2)
        self.assertError(mapping.check(self.root, rel, stage_gate=SA_GATE), "MAPK1", "STAGE_GATE outputs")


MENTION = "seeds and mapping files may be named only on the DATA_INPUT line"


class OrchestratorMentionTests(DataInputFixture):
    """Seeds and mapping files under runs/orchestrator reach a specialist only through DATA_INPUT."""

    def setUp(self):
        super().setUp()
        self.add_source()
        self.write_seeds(self.SEEDS_REL, ["KRAS", "EGFR"])
        self.approve_seeds("dec-seeds-1", self.SEEDS_REL, ["EGFR", "KRAS"])

    def assertRefused(self, role, prompt, fragment=MENTION):
        result = self.hook(role, prompt)
        self.assertEqual(result.returncode, 2, (prompt, result.stderr))
        self.assertIn(fragment, result.stderr, prompt)

    def assertAllowed(self, role, prompt):
        result = self.hook(role, prompt)
        self.assertEqual(result.returncode, 0, (prompt, result.stderr))

    def test_seeds_without_data_input_refused(self):
        self.assertRefused("network-curator", f"Build the network from {self.SEEDS_REL}.")
        self.assertRefused("network-curator", f"Build.\nSeeds: `{self.SEEDS_REL}`")

    def test_seeds_under_an_unusual_name_refused(self):
        odd = "runs/orchestrator/notes/genes_for_curator.JSON"
        (self.root / odd).parent.mkdir(parents=True)
        shutil.copyfile(self.root / self.SEEDS_REL, self.root / odd)
        self.assertRefused("network-curator", f"Build the network from {odd}")
        # Alongside a valid seeds DATA_INPUT the second file is still refused.
        self.assertAllowed("network-curator", self.seeds_task())
        self.assertRefused("network-curator", f"{self.seeds_task()}\nAlso use {odd}.")
        # And alongside the data-session form.
        self.assertRefused("network-curator", f"{self.neko_task()}\nAlso use {odd}.")

    def test_mapping_with_only_stage_gate_refused(self):
        self.stage_gate_ready()
        self.assertAllowed("boolean-dynamics-modeler", f"{STAGE_GATE}\nImport and simulate.")
        self.assertRefused("boolean-dynamics-modeler",
                           f"{STAGE_GATE}\nSimulate the scenarios listed in {self.mapping_rel}.")

    def test_second_mapping_or_seeds_alongside_data_input_refused(self):
        self.stage_gate_ready()
        other, _ = self.complete("other")
        self.assertRefused("boolean-dynamics-modeler", f"{self.maboss_task()}\nCompare with {other}.")
        self.assertRefused("boolean-dynamics-modeler", f"{self.maboss_task()}\nSeeds were {self.SEEDS_REL}.")
        self.assertRefused("network-curator", f"{self.seeds_task()}\nMapping: {self.mapping_rel}.")

    def test_data_input_artifact_mentioned_again_allowed(self):
        self.stage_gate_ready()
        self.assertAllowed("boolean-dynamics-modeler",
                           f"{self.maboss_task()}\nThe mapping (`{self.mapping_rel}`) is fixed.")
        self.assertAllowed("network-curator", f"{self.seeds_task()}\nSeeds file: \"{self.SEEDS_REL}\".")
        self.assertAllowed("network-curator",
                           f"{self.seeds_task()}\nSeeds file: {self.SEEDS_REL.replace('/', chr(92))}.")

    def test_other_orchestrator_files_allowed(self):
        base = self.root / "runs" / "orchestrator" / "luad"
        files = {"runs.json": '{"runs": []}', "summary.md": "# Summary\n", "notes.json": '{"note": "x"}',
                 "broken.json": '{"seeds": [', "list.json": "[1, 2]", "CHANGES.md": "edits\n"}
        for name, text in files.items():
            (base / name).write_text(text, encoding="utf-8")
        mentions = " ".join(f"runs/orchestrator/luad/{name}," for name in files)
        mentions += " runs/orchestrator/luad/absent.json runs/orchestrator/luad"
        self.assertAllowed("network-curator", f"Build from EGFR, KRAS. Context: {mentions}")
        self.stage_gate_ready()
        self.assertAllowed("boolean-dynamics-modeler", f"{STAGE_GATE}\nImport and simulate. Context: {mentions}")
        self.assertAllowed("boolean-dynamics-modeler", f"{self.maboss_task()}\nContext: {mentions}")

    def test_spelling_variants_detected(self):
        spaced = "runs/orchestrator/kras-seeds/seeds copy.json"
        shutil.copyfile(self.root / self.SEEDS_REL, self.root / spaced)
        for variant in (self.SEEDS_REL.replace("/", "\\"), "RUNS/Orchestrator/KRAS-SEEDS/Seeds.JSON",
                        "runs\\\\orchestrator//kras-seeds/seeds.json", "runs／orchestrator／kras-seeds／seeds.json",
                        "runs/orches​trator/kras-seeds/seeds.json", f"./{self.SEEDS_REL}",
                        f"{self.root}/{self.SEEDS_REL}", f"runs/orchestrator/luad/../kras-seeds/seeds.json",
                        f"<{self.SEEDS_REL}>", f"({self.SEEDS_REL});", f"'{self.SEEDS_REL}'", spaced):
            self.assertRefused("network-curator", f"Build the network from {variant}")

    def test_gate_message_and_unreadable_files(self):
        with self.assertRaisesRegex(ValueError, f"{self.SEEDS_REL}.*{MENTION}"):
            gate.check_data_input(self.root, "network_curator", f"Build from {self.SEEDS_REL}")
        # An unexpected failure while inspecting a mentioned file fails closed through the hook.
        with mock.patch.object(gate, "_model_input_kind", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                gate.check_data_input(self.root, "network_curator", f"Build from {self.SEEDS_REL}")
        deep = self.root / "runs" / "orchestrator" / "luad" / "deep.json"
        deep.write_text("[" * 100000, encoding="utf-8")
        result = self.hook("network-curator", "Build from runs/orchestrator/luad/deep.json")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("blocked", result.stderr)


if __name__ == "__main__":
    unittest.main()

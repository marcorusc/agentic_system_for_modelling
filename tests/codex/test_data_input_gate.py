"""DATA_INPUT dispatch checks: NeKo seeds and MaBoSS mappings consume only approved, hash-checked data."""
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

from scripts import gate, state
from tests.data.test_mapping import BNET, BNET_TEXT, NEKO, MappingFixture, sha

REFUSAL = "brief references data-analyst artifacts without a DATA_INPUT line; see CLAUDE.md"
HOOK = state.ROOT / ".claude" / "scripts" / "stage_gate_guard.py"
OUTPUTS = ["Proliferation", "Survival"]
STAGE_GATE = "STAGE_GATE " + json.dumps({"upstream_session_id": NEKO, "outputs": OUTPUTS})


class DataInputFixture(MappingFixture):
    def setUp(self):
        super().setUp()
        self.seeds = f"{self.base}/proposals/P3_seed_genes.csv"
        self.mapping_rel, self.mapping_data = self.complete()
        self.approve_mapping("dec-map-1", self.mapping_rel)
        for name in ("CURRENT_STATE.md", "VALIDATION_PLAN.md"):
            shutil.copyfile(state.ROOT / "templates" / name, self.root / name)

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

    def test_neko_newest_approval_is_used(self):
        self.approve("dec-data-2", ["P3"])
        self.assertEqual(gate.check_data_input(self.root, "network_curator", self.neko_task())["approval_id"],
                         "dec-data-2")

    def test_neko_untimed_approval_among_timed_is_ambiguous(self):
        ref = {"path": f"{self.base}/handoff.json", "sha256": sha(self.root / self.base / "handoff.json")}
        record = {"id": "dec-data-hand", "kind": "stage_approval", "stage": "data", "session_id": self.sid,
                  "outputs": ["P3"], "artifact": ref, "approved_by": "researcher", "authorization": "ok"}
        decisions = self.root / "DECISIONS.md"
        decisions.write_text(decisions.read_text(encoding="utf-8").rstrip()
                             + "\n\n<!-- governance-record -->\n```json\n" + json.dumps(record) + "\n```\n",
                             encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cannot order data approvals"):
            gate.check_data_input(self.root, "network_curator", self.neko_task())

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
        # The newest approval of the session governs; it no longer approves P3.
        self.approve("dec-data-2", ["P1", "P2"])
        with self.assertRaisesRegex(ValueError, "not in the approved outputs of decision dec-data-2"):
            gate.check_data_input(self.root, "network_curator", self.neko_task())
        # A handoff changed after approval invalidates the approval.
        handoff = self.root / self.base / "handoff.json"
        handoff.write_text(handoff.read_text(encoding="utf-8") + " ", encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()

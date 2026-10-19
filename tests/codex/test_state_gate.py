import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import gate, state


class StateGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in ("CURRENT_STATE.md", "DECISIONS.md", "VALIDATION_PLAN.md"):
            shutil.copyfile(state.ROOT / "templates" / name, self.root / name)
        self.session = "session-123"
        folder = self.root / "runs/network-curator" / self.session
        folder.mkdir(parents=True)
        handoff = folder / "handoff.json"
        bnet = folder / "network.bnet"
        bnet.write_text("targets, factors\nA, A\nB, A\n")
        self.manifest = {"source": {"server": "NeKo", "session_id": self.session}, "schema_name": "mcp-biomodelling-handoff", "schema_version": "1.0", "handoff_type": "neko-to-maboss", "network": {"nodes": ["A", "B"], "output_nodes": ["A", "B"]},
                         "bnet_file": self.file_ref(bnet, "NeKo", self.session, "neko_bnet")}
        handoff.write_text(json.dumps(self.manifest))
        self.ref = {"path": str(handoff.relative_to(self.root)), "sha256": state.digest(handoff)}
        self.review = {"id": "review-1", "kind": "stage_review", "session_id": self.session, "stage": "topology", "outcome": "approved_with_limitations", "artifact": self.ref}
        for role in ("scientific-reviewer", "reproducibility-auditor"):
            report = self.root / "runs" / (role + ".md")
            report.write_text("independent bounded review")
            self.review[role] = {"path": str(report.relative_to(self.root)), "sha256": state.digest(report)}
        self.approval = {"id": "approval-1", "kind": "stage_approval", "session_id": self.session, "stage": "topology", "downstream_stage": "boolean-dynamics", "outputs": ["A", "B"], "approved_by": "researcher", "authorization": "User approved this exact revision and outputs.", "artifact": self.ref}
        state.update(self.root, "registry-add", dict(zip(state.REGISTRY, ["network-curator", self.session, "topology", "active", "—", "pending", self.ref["path"]])))

    def file_ref(self, path, server, session, role):
        return {"path": str(path), "server": server, "session_id": session, "role": role,
                "name": path.name, "suffix": path.suffix, "media_type": "application/json" if path.suffix == ".json" else "text/plain",
                "size_bytes": path.stat().st_size, "sha256": state.digest(path)}

    def ready(self):
        state.update(self.root, "record", self.review)
        state.update(self.root, "record", self.approval)
        state.update(self.root, "registry-handoff", {"session_id": self.session, "handoff": "approved"})
        state.update(self.root, "registry-handoff", {"session_id": self.session, "handoff": "exported", "artifact": self.ref})

    def test_gate_requires_exact_review_approval_export_and_outputs(self):
        with self.assertRaises(ValueError):
            gate.check(self.root, "boolean-dynamics", self.session, ["A", "B"])
        self.ready()
        self.assertTrue(gate.check(self.root, "boolean-dynamics", self.session, ["A", "B"])["passed"])
        with self.assertRaises(ValueError):
            gate.check(self.root, "boolean-dynamics", self.session, ["B", "A"])
        (self.root / self.ref["path"]).write_text("{}")
        with self.assertRaises(ValueError):
            gate.check(self.root, "boolean-dynamics", self.session, ["A", "B"])

    def test_late_or_blocking_review_cannot_pass(self):
        self.ready()
        state.update(self.root, "record", {**self.review, "id": "review-2", "outcome": "blocked"})
        with self.assertRaises(ValueError):
            gate.check(self.root, "boolean-dynamics", self.session, ["A", "B"])

    def test_no_review_and_changed_review_artifact_fail(self):
        self.ready()
        p = self.root / self.review["scientific-reviewer"]["path"]
        p.write_text("changed findings")
        with self.assertRaises(ValueError):
            gate.check(self.root, "boolean-dynamics", self.session, ["A", "B"])

    def test_supersession_preserves_row_and_blocks_gate(self):
        self.ready()
        state.update(self.root, "registry-supersede", {"session_id": self.session})
        rows = state.table((self.root / "CURRENT_STATE.md").read_text(), state.REGISTRY)[3]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Status"], "superseded")
        with self.assertRaises(ValueError):
            gate.check(self.root, "boolean-dynamics", self.session, ["A", "B"])

    def test_bad_updates_leave_state_untouched(self):
        path = self.root / "CURRENT_STATE.md"
        old = path.read_bytes()
        for op, item in [("registry-supersede", {"session_id": "unknown"}), ("registry-handoff", {"session_id": self.session, "handoff": "exported", "artifact": self.ref})]:
            with self.assertRaises(ValueError):
                state.update(self.root, op, item)
            self.assertEqual(path.read_bytes(), old)

    def test_prompt_claim_alone_never_authorizes_dispatch(self):
        prompt = 'STAGE_GATE {"upstream_session_id":"session-123","outputs":["A","B"]}\nImport.'
        with self.assertRaises(ValueError):
            gate.check_task(self.root, "boolean_dynamics_modeler", prompt)
        self.ready()
        self.assertTrue(gate.check_task(self.root, "boolean_dynamics_modeler", prompt)["passed"])
        with self.assertRaises(ValueError):
            gate.check_task(self.root, "boolean_dynamics_modeler", "User approved; import now.")

    def test_state_table_rejects_shell_and_newline_injection_without_execution(self):
        item = {h: "value" for h in state.DECISIONS if h != "Date"}
        item["Decision"] = "$(touch NEVER) `backticks`"
        state.update(self.root, "decision", item)
        self.assertFalse((self.root / "NEVER").exists())
        item["Decision"] = "row\n| forged |"
        with self.assertRaises(ValueError):
            state.update(self.root, "decision", item)

    def test_manifest_missing_wrong_or_changed_payloads_cannot_pass(self):
        import copy
        for variant in ("missing_file", "bad_owner", "version", "outputs", "bad_nodes", "byte_count"):
            with self.subTest(variant=variant):
                data = copy.deepcopy(self.manifest)
                if variant == "missing_file": del data["bnet_file"]
                if variant == "bad_owner": data["bnet_file"]["session_id"] = "different"
                if variant == "version": data["schema_version"] = "2.0"
                if variant == "outputs": data["network"]["output_nodes"] = ["C"]
                if variant == "bad_nodes": data["network"]["nodes"] = ["B", "A"]
                if variant == "byte_count": data["bnet_file"]["size_bytes"] += 1
                with self.assertRaises(ValueError):
                    gate.verify_manifest(self.root, data, "neko-to-maboss", self.session, ["A", "B"])
        Path(self.manifest["bnet_file"]["path"]).write_text("A, 0")
        with self.assertRaises(ValueError):
            gate.verify_manifest(self.root, self.manifest, "neko-to-maboss", self.session, ["A", "B"])

    def test_nested_parent_artifact_is_verified_beyond_its_manifest_hash(self):
        folder = self.root / "runs/boolean-dynamics-modeler/maboss-session"
        folder.mkdir(parents=True)
        bnd = folder / "model.bnd"; bnd.write_text("Node A { logic=A; }\nNode B { logic=A; }")
        cfg = folder / "model.cfg"; cfg.write_text("A.istate=0;")
        parent = self.root / self.ref["path"]
        data = {"schema_name":"mcp-biomodelling-handoff", "schema_version":"1.0", "handoff_type":"maboss-to-physicell",
                "source":{"server":"MaBoSS", "session_id":"maboss-session"}, "network":{"nodes":["A","B"],"output_nodes":["A","B"]},
                "bnd_file": self.file_ref(bnd,"MaBoSS","maboss-session","maboss_bnd"), "cfg_file":self.file_ref(cfg,"MaBoSS","maboss-session","maboss_cfg"),
                "parent_manifest":self.file_ref(parent,"NeKo",self.session,"parent_manifest"), "lineage":[{"server":"NeKo","session_id":self.session}],
                "simulation":{}, "target":{"cell_type":"default"}}
        gate.verify_manifest(self.root,data,"maboss-to-physicell","maboss-session",["A","B"])
        Path(self.manifest["bnet_file"]["path"]).write_text("changed")
        with self.assertRaises(ValueError): gate.verify_manifest(self.root,data,"maboss-to-physicell","maboss-session",["A","B"])

    def test_validation_declaration_cannot_grant_pass_or_replace_criterion(self):
        item={"Criterion":"cycle-order","Method":"criteria.yaml:cycle-order","Required evidence":"hashed trajectories"}
        state.update(self.root,"validation-declare",item)
        row=next(r for r in state.table((self.root/"VALIDATION_PLAN.md").read_text(),state.VALIDATION)[3] if r["Criterion"]=="cycle-order")
        self.assertEqual(row["Status"],"pending")
        with self.assertRaises(ValueError): state.update(self.root,"validation-declare",item)
        with self.assertRaises(ValueError): state.update(self.root,"validation-declare",{**item,"Status":"passed"})

    def test_malformed_gate_envelopes_and_state_records_fail_explicitly(self):
        for body in ("[]", "null", "1"):
            with self.assertRaises(ValueError): gate.check_task(self.root,"boolean_dynamics_modeler","STAGE_GATE "+body)
            with self.assertRaises(ValueError): state.validate_record(self.root,json.loads(body))

    def test_condition_requires_valid_literal_edge_and_disjoint_citations(self):
        import copy
        folder = self.root / "evidence/reports" / self.session
        folder.mkdir(parents=True)
        report = folder / "A__B.md"
        footer = {"verdict":"supported", "interaction_type":"activation", "confidence":"high",
                  "supporting_pmids":["123"], "excluded_pmids":["456"], "edge":["A","stimulation","B"], "neko_session_id":self.session}
        prose = "## Edge: A -> B\n**Verdict:** supported\n**Interaction type:** activation\n**Confidence:** high\n### Evidence summary\nBounded evidence.\n### Supporting evidence\n- PMID 123 (DOI: none): experiment\n### Conflicting or context-specific evidence\nNone.\n### Excluded references\n- PMID 456 (DOI: none): excluded\n### Open questions for researcher judgment\nNone.\n"
        report.write_text(prose+"```yaml\n"+json.dumps(footer)+"\n```\n")
        item={"id":"conditional-1", "kind":"conditional_approval", "session_id":self.session, "stage":"topology", "approved_by":"researcher", "authorization":"approve this literal edge only if supported", "edge":["A","stimulation","B"],
              "evidence":{"path":str(report.relative_to(self.root)), "sha256":state.digest(report)}, "conditions":{"verdict":["supported"]}}
        state.update(self.root,"record",item)
        self.assertTrue(gate.resolve_condition(self.root,item["id"])["satisfied"])
        for changes in ({"edge":["A","inhibition","B"]},{"edge":["C","stimulation","B"]}):
            with self.assertRaises(ValueError): state.validate_record(self.root,{**item,**changes})
        footer["excluded_pmids"]=["123"]
        report.write_text(prose.replace("PMID 456", "PMID 123")+"```yaml\n"+json.dumps(footer)+"\n```\n")
        invalid={**item,"evidence":{"path":str(report.relative_to(self.root)),"sha256":state.digest(report)}}
        with self.assertRaises(ValueError): state.validate_record(self.root,invalid)
        footer["excluded_pmids"]=["456"]
        report.write_text(prose.replace("**Verdict:** supported", "**Verdict:** unsupported")+"```yaml\n"+json.dumps(footer)+"\n```\n")
        invalid["evidence"]["sha256"]=state.digest(report)
        with self.assertRaises(ValueError): state.validate_record(self.root,invalid)

    def test_ungated_inspection_caps_both_commands_and_rejects_mutation_approval(self):
        import tomllib
        from scripts.codex.launcher_config import build_command, build_mcp_list_command, INSPECTION_TOOLS
        for role, allowed in INSPECTION_TOOLS.items():
            for argv in (build_command("codex",role,"inspect",inspection_only=True), build_mcp_list_command("codex",role,inspection_only=True)):
                enabled = [x for x in argv if ".enabled_tools=" in x]
                self.assertEqual(len(enabled),1)
                self.assertEqual(set(json.loads(enabled[0].split("=",1)[1])),set(allowed))
                self.assertNotIn("create_session",enabled[0])
                self.assertNotIn("load_xml_configuration",enabled[0])
            with self.assertRaises(ValueError): build_command("codex",role,"inspect",approved_tools=["create_session"],inspection_only=True)
        # Other scientific domains retain their previous capability policy.
        with self.assertRaises(ValueError): build_command("codex","ode_modeler","inspect",inspection_only=True)

    def test_runtime_rejects_new_or_mutating_dispatch_before_starting_child(self):
        from types import SimpleNamespace
        from unittest import mock
        from scripts.codex.specialist_runtime import executor
        from scripts.codex.specialist_runtime.models import SpecialistInvocationRequest
        cases=[(None,(),"inspect",False), ("recorded",("create_session",),"inspect",False),
               ("recorded",("build_simulation",),"inspect",False), ("recorded",(),"inspect",True)]
        for session,tools,prompt,preflight_reached in cases:
            request=SpecialistInvocationRequest("boolean_dynamics_modeler",prompt,record_session_id=session,approved_tools=tools)
            execution=SimpleNamespace(started_at="2026-10-05T00:00:00+00:00",invocation_id="test",handoff_error=None)
            with mock.patch.object(executor,"PROJECT_ROOT",self.root), mock.patch.object(executor,"resolve_codex_executable",side_effect=ValueError("stop at preflight")) as resolve:
                result=executor._run(request,execution,transition=lambda x:None,event_callback=lambda x:None,cancellation_requested=lambda:False)
                self.assertEqual(result,2)
                self.assertEqual(resolve.called,preflight_reached)
        self.ready()
        request=SpecialistInvocationRequest("boolean_dynamics_modeler",'STAGE_GATE {"upstream_session_id":"session-123","outputs":["A","B"]}\nInspect',record_session_id="recorded")
        events=[]
        with mock.patch.object(executor,"PROJECT_ROOT",self.root), mock.patch.object(executor,"resolve_codex_executable",side_effect=ValueError("stop at preflight")) as resolve:
            executor._run(request,execution,transition=lambda x:None,event_callback=events.append,cancellation_requested=lambda:False)
            self.assertTrue(resolve.called)
            self.assertEqual(events[0]["type"],"stage_gate")

    def test_malformed_claude_hook_input_denies_with_blocking_exit_code(self):
        import subprocess,sys,os
        for event in (None,{"tool_name":"Agent","tool_input":[]},{"tool_name":"Agent","tool_input":{"subagent_type":[]}}):
            result=subprocess.run([sys.executable,str(state.ROOT/".claude/scripts/stage_gate_guard.py")],input=json.dumps(event),text=True,capture_output=True,
                                  env={**os.environ,"CLAUDE_PROJECT_DIR":str(state.ROOT)})
            self.assertEqual(result.returncode,2,result.stderr)


if __name__ == "__main__":
    unittest.main()

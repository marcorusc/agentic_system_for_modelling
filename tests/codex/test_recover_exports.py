"""recover.py copies a specialist's server exports out of the transient artifact store."""
from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.capture import recover
from scripts.capture.transcripts import project_slug

AID = "agent-x1"
SESSION = "sess-1"
SUMMARY_HINT = "Set verbosity='preview' or 'full' for more details."


def file_summary(path: Path, session=SESSION) -> dict:
    """artifact_file_summary(path, session_id=...) as model_dump(mode='json')."""
    suffix = path.suffix.lower()
    media = {".sif": "text/tab-separated-values", ".json": "application/json", ".bnet": "text/plain",
             ".bnd": "text/plain", ".cfg": "text/plain", ".xml": "application/xml", ".csv": "text/csv"}
    size = path.stat().st_size if path.exists() else None
    return {"session_id": session, "name": path.name, "path": str(path), "suffix": suffix,
            "media_type": media.get(suffix), "size_bytes": size}


def neko_export(fmt: str, path: Path, session=SESSION) -> dict:
    """NeKoNetworkExportResult(server='NeKo', ...) as structuredContent."""
    return {"server": "NeKo", "session_id": session, "format": fmt, "file": file_summary(path),
            "renamed_nodes": [], "duplicate_rules_removed": []}


def neko_text(fmt: str, path: Path) -> str:
    return {"sif": f"SIF exported: {path}. {SUMMARY_HINT}", "history": f"History exported: {path}"}[fmt]


class ExportsBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root, self.troot, self.aroot = base / "proj", base / "projects", base / "artifacts"
        for d in (self.root, self.troot, self.aroot):
            d.mkdir()
        self.base = base
        env = mock.patch.dict(os.environ, {"MCP_BIOMODELLING_ARTIFACT_ROOT": str(self.aroot)})
        env.start()
        self.addCleanup(env.stop)
        self.neko = self.aroot / "NeKo" / SESSION
        self.neko.mkdir(parents=True)

    def artifact(self, relative: str, content: bytes, root: Path | None = None) -> Path:
        path = (root or self.neko) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def transcript(self, results, *, prefix="neko", create=True, aid=AID, main="uuid-1"):
        """results: list of (tool, input, tool_result_content[, extra event fields])."""
        ev = [{"type": "user", "timestamp": "2026-10-05T00:00:00Z", "message": {"content": "Curate"}}]
        if create:
            ev += [{"type": "assistant", "message": {"id": "c", "content": [
                {"type": "tool_use", "id": "create", "name": f"mcp__{prefix}-agent__create_session", "input": {}}]}},
                {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "create",
                                                          "content": f"Session created: {SESSION}"}]}}]
        for n, item in enumerate(results):
            tool, arguments, content = item[:3]
            extra = item[3] if len(item) > 3 else {}
            ev.append({"type": "assistant", "message": {"id": f"m{n}", "content": [
                {"type": "tool_use", "id": f"call{n}", "name": f"mcp__{prefix}-agent__{tool}", "input": arguments}]}})
            block = {"type": "tool_result", "tool_use_id": f"call{n}", "content": content}
            block.update(extra.get("block", {}))
            event = {"type": "user", "message": {"content": [block]}}
            event.update(extra.get("event", {}))
            ev.append(event)
        ev.append({"type": "assistant", "timestamp": "2026-10-05T00:00:10Z", "message": {"id": "end", "content": [
            {"type": "tool_use", "id": "hand", "name": "SubagentHandback", "input": {"message": "# Report\n\nDone."}}]}})
        d = self.troot / project_slug(self.root) / main / "subagents"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"agent-{aid}.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in ev), encoding="utf-8")
        return path

    @staticmethod
    def structured(text: str, payload: dict) -> str:
        """CallToolResult(content=[text], structuredContent=payload) serialized as tool_result content."""
        return json.dumps({"content": [{"type": "text", "text": text}], "structuredContent": payload})

    def run_recover(self, specialist="network-curator"):
        return recover.recover(self.root, specialist, AID, None, self.troot)

    def exports_dir(self, specialist="network-curator"):
        return self.root / "runs" / specialist / SESSION / "exports" / AID

    def manifest(self, specialist="network-curator"):
        return json.loads((self.exports_dir(specialist) / "exports.json").read_text(encoding="utf-8"))

    def snapshot(self):
        return {p: p.read_bytes() for p in (self.root / "runs").rglob("*") if p.is_file()}


class CaptureTests(ExportsBase):
    def test_captures_neko_sif_and_history_exports(self):
        sif = self.artifact("Network.sif", b"EGFR\t1\tKRAS\nKRAS\t1\tBRAF\n")
        hist = self.artifact("network.0123abcd.history.json", b'{"states":[]}')
        self.transcript([
            ("export_network", {"format": "sif", "session_id": SESSION},
             self.structured(neko_text("sif", sif), neko_export("sif", sif))),
            ("export_network", {"format": "history", "session_id": SESSION},
             self.structured(neko_text("history", hist), neko_export("history", hist))),
        ])
        result = self.run_recover()
        self.assertEqual(result["status"], "recorded")
        out = self.exports_dir()
        self.assertEqual((out / "Network.sif").read_bytes(), sif.read_bytes())
        self.assertEqual((out / hist.name).read_bytes(), hist.read_bytes())
        manifest = self.manifest()
        self.assertEqual(manifest["session_id"], SESSION)
        self.assertEqual(manifest["invocation_id"], AID)
        rows = {row["format"]: row for row in manifest["exports"]}
        self.assertEqual(set(rows), {"sif", "history"})
        for fmt, src in (("sif", sif), ("history", hist)):
            row = rows[fmt]
            self.assertEqual(row["tool"], "export_network")
            self.assertEqual(row["source_path"], str(src))
            self.assertEqual(row["dest_path"], f"runs/network-curator/{SESSION}/exports/{AID}/{src.name}")
            self.assertEqual(row["sha256"], hashlib.sha256(src.read_bytes()).hexdigest())
            self.assertEqual(row["bytes"], len(src.read_bytes()))
        self.assertEqual([e["format"] for e in result["exports"]["copied"]], ["sif", "history"])

    def test_text_prefix_fallback_and_tool_use_result_shape(self):
        sif = self.artifact("Network.sif", b"A\t1\tB\n")
        hist = self.artifact("network.ff.history.json", b"{}")
        self.transcript([
            # prose only (no structured content): fall back to the exact text prefix
            ("export_network", {"format": "sif"}, [{"type": "text", "text": neko_text("sif", sif)}]),
            # structured content carried on the event's toolUseResult
            ("export_network", {"format": "history"}, [{"type": "text", "text": "ok"}],
             {"event": {"toolUseResult": {"structuredContent": neko_export("history", hist)}}}),
        ])
        self.run_recover()
        self.assertEqual({r["format"] for r in self.manifest()["exports"]}, {"sif", "history"})

    def test_structured_field_preferred_over_prose(self):
        real = self.artifact("network.aa.history.json", b"{}")
        decoy = self.artifact("network.bb.history.json", b"{}")
        self.transcript([("export_network", {"format": "history"},
                          self.structured(neko_text("history", decoy), neko_export("history", real)))])
        self.run_recover()
        self.assertEqual([r["source_path"] for r in self.manifest()["exports"]], [str(real)])

    def test_failed_and_unrelated_tool_results_ignored(self):
        sif = self.artifact("Network.sif", b"A\t1\tB\n")
        self.transcript([
            ("export_network", {"format": "sif"}, self.structured(neko_text("sif", sif), neko_export("sif", sif)),
             {"block": {"is_error": True}}),
            ("list_bnet_files", {}, self.structured("files", {"server": "NeKo", "session_id": SESSION,
                                                               "file": file_summary(sif)})),
        ])
        result = self.run_recover()
        self.assertEqual(result["exports"]["copied"], [])
        self.assertFalse((self.root / "runs/network-curator" / SESSION / "exports").exists())

    def test_rejects_export_outside_artifact_session_dir(self):
        other = self.artifact("Network.sif", b"X\t1\tY\n", root=self.aroot / "NeKo" / "sess-other")
        outside = self.base / "elsewhere" / "network.cc.history.json"
        outside.parent.mkdir()
        outside.write_bytes(b"{}")
        link = self.neko / "linked.history.json"
        link.symlink_to(outside)
        wrong_server = self.artifact("model.bnd", b"x", root=self.aroot / "MaBoSS" / SESSION)
        dotdot = Path(f"{self.neko}/../sess-other/Network.sif")
        self.transcript([("export_network", {"format": f}, self.structured(neko_text("history", p),
                                                                            neko_export("history", p)))
                         for f, p in (("sif", other), ("history", outside), ("history", link),
                                      ("history", wrong_server), ("history", dotdot))])
        result = self.run_recover()
        rejected = result["exports"]["rejected"]
        self.assertEqual(sorted(r["source_path"] for r in rejected),
                         sorted(map(str, (other, outside, link, wrong_server, dotdot))))
        self.assertTrue(all(r.get("rejected") is True and r.get("reason") for r in rejected))
        self.assertEqual(result["exports"]["copied"], [])
        copied = [p.name for p in self.exports_dir().iterdir()]
        self.assertEqual(copied, ["exports.json"])
        self.assertTrue(all(row.get("rejected") for row in self.manifest()["exports"]))

    def test_rerun_is_noop_and_differing_content_fails(self):
        sif = self.artifact("Network.sif", b"A\t1\tB\n")
        self.transcript([("export_network", {"format": "sif"},
                          self.structured(neko_text("sif", sif), neko_export("sif", sif)))])
        self.run_recover()
        snap = self.snapshot()
        again = self.run_recover()
        self.assertEqual(again["status"], "already-recorded")
        self.assertEqual(self.snapshot(), snap)
        sif.write_bytes(b"A\t-1\tB\n")
        with self.assertRaisesRegex(ValueError, "refusing overwrite"):
            self.run_recover()
        self.assertEqual(self.snapshot(), snap)

    def test_missing_source_recorded_not_fatal(self):
        gone = self.neko / "network.dd.history.json"
        self.transcript([("export_network", {"format": "history"},
                          self.structured(neko_text("history", gone), neko_export("history", gone)))])
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)}), \
                redirect_stdout(out), redirect_stderr(err):
            code = recover.main(["--specialist", "network-curator", "--agent-id", AID,
                                 "--transcript-root", str(self.troot)])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(self.manifest()["exports"],
                         [{"tool": "export_network", "format": "history", "source_path": str(gone), "missing": True}])
        self.assertIn("missing", (out.getvalue() + err.getvalue()).lower())
        self.assertEqual(out.getvalue().splitlines()[-1], f"RECOVERED network-curator {SESSION} recorded")

    def test_copied_then_missing_source_rerun_is_noop(self):
        sif = self.artifact("Network.sif", b"A\t1\tB\n")
        self.transcript([("export_network", {"format": "sif"},
                          self.structured(neko_text("sif", sif), neko_export("sif", sif)))])
        self.run_recover()
        snap = self.snapshot()
        sif.unlink()
        self.run_recover()
        self.assertEqual(self.snapshot(), snap)

    def test_no_exports_no_dir(self):
        self.transcript([])
        result = self.run_recover()
        self.assertEqual(result["exports"], {"path": None, "copied": [], "missing": [], "rejected": []})
        self.assertFalse((self.root / "runs/network-curator" / SESSION / "exports").exists())

    def test_ode_modeler_excluded(self):
        ode = self.artifact("model.json", b"{}", root=self.aroot / "BioMASS" / SESSION)
        self.transcript([("export_network", {"format": "sif"},
                          self.structured(neko_text("sif", ode), neko_export("sif", ode)))], prefix="biomass")
        result = self.run_recover(specialist="ode-modeler")
        self.assertEqual(result["status"], "recorded")
        self.assertIsNone(result["exports"])
        self.assertFalse((self.root / "runs/ode-modeler" / SESSION / "exports").exists())

    def test_already_recorded_still_captures_exports(self):
        sif = self.artifact("Network.sif", b"A\t1\tB\n")
        self.transcript([])
        self.run_recover()
        # the hook-recorded invocation predates export capture: same agent, exports now visible
        self.transcript([("export_network", {"format": "sif"},
                          self.structured(neko_text("sif", sif), neko_export("sif", sif)))])
        with mock.patch.object(recover, "record", side_effect=AssertionError("must not re-record")):
            result = self.run_recover()
        self.assertEqual(result["status"], "already-recorded")
        self.assertEqual((self.exports_dir() / "Network.sif").read_bytes(), sif.read_bytes())

    def test_maboss_and_physicell_exports(self):
        mroot = self.aroot / "MaBoSS" / SESSION
        bnd, cfg = self.artifact("run.bnd", b"Node A {}", root=mroot), self.artifact("run.cfg", b"$x=1;", root=mroot)
        self.transcript([("export_maboss_bnd_cfg", {"prefix": "run"}, self.structured(
            f"Exported current MaBoSS model successfully.\n  BND: {bnd}\n  CFG: {cfg}",
            {"server": "MaBoSS", "session_id": SESSION, "prefix": "run", "model_revision": None,
             "output_nodes": [], "internal_nodes": [], "overwrite": False,
             "bnd_file": file_summary(bnd), "cfg_file": file_summary(cfg)}))], prefix="maboss")
        self.run_recover(specialist="boolean-dynamics-modeler")
        rows = self.manifest("boolean-dynamics-modeler")["exports"]
        self.assertEqual({(r["tool"], r["format"]) for r in rows},
                         {("export_maboss_bnd_cfg", "bnd"), ("export_maboss_bnd_cfg", "cfg")})

    def test_physicell_exports(self):
        proot = self.aroot / "PhysiCell" / SESSION
        xml = self.artifact("PhysiCell_settings.xml", b"<x/>", root=proot)
        bundle = self.artifact("bundles/b1.zip", b"PK", root=proot)
        self.transcript([
            ("export_xml_configuration", {}, self.structured(f"**File:** {xml}", {
                "server": "PhysiCell", "session_id": SESSION, "file": file_summary(xml), "source": "created",
                "modification_count": 0, "substrates": [], "cell_types": [], "progress": 0})),
            ("export_configuration_bundle", {}, self.structured("bundle", {
                "server": "PhysiCell", "session_id": SESSION, "model_revision": "r", "bundle_id": "b1",
                "bundle": str(bundle), "manifest": "manifest.json (inside bundle)",
                "status": "configuration_complete", "requirements": []})),
        ], prefix="physicell")
        self.run_recover(specialist="multicellular-configurator")
        rows = self.manifest("multicellular-configurator")["exports"]
        self.assertEqual({(r["tool"], r["format"]) for r in rows},
                         {("export_xml_configuration", "xml"), ("export_configuration_bundle", "bundle")})

    def test_cli_lists_exports_and_keeps_last_line(self):
        sif = self.artifact("Network.sif", b"A\t1\tB\n")
        self.transcript([("export_network", {"format": "sif"},
                          self.structured(neko_text("sif", sif), neko_export("sif", sif)))])
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)}), redirect_stdout(out):
            code = recover.main(["--specialist", "network-curator", "--agent-id", AID,
                                 "--transcript-root", str(self.troot)])
        self.assertEqual(code, 0)
        lines = out.getvalue().splitlines()
        self.assertTrue(any(l.startswith("export: export_network sif ") and "Network.sif" in l for l in lines), lines)
        self.assertEqual(lines[-1], f"RECOVERED network-curator {SESSION} recorded")


if __name__ == "__main__":
    unittest.main()

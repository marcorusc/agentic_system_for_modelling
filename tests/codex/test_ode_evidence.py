from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.codex.ode_evidence import (
    ReportValidationError,
    destination,
    validate_ode_report,
    write_ode_report,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE = {
    "pmid": "12345678",
    "doi": "10.1000/synthetic-test",
    "location": "Table 1",
    "access": "full-text",
    "limitations": "Synthetic test citation; no biological evidence.",
    "context": "Synthetic software test only.",
    "finding": "Test fixture finding.",
    "stance": "supports",
}
QUANTITY = {
    "name": "synthetic rate",
    "value": "0.1–0.2",
    "units": "min^-1",
    "source": "12345678",
    "location": "Table 1",
}


def report(*, kind="mechanism", verdict="insufficient evidence", sources=None, quantities=None):
    return f"""## ODE claim: binding
**Claim:** The specified molecular states bind.
**Kind:** {kind}
**Verdict:** {verdict}
**Confidence:** low
**Biological context:** Synthetic software test only.

### Evidence summary
No biological conclusion is established by this software fixture.
### Sources
{json.dumps([] if sources is None else sources)}
### Conflicts
Unknown.
### Reported quantities
{json.dumps([] if quantities is None else quantities)}
### Open questions
Primary experimental evidence is needed.
"""


class ODEReportValidationTests(unittest.TestCase):
    def test_insufficient_evidence_may_have_no_sources(self):
        parsed = validate_ode_report(report(), "binding")
        self.assertEqual(parsed["sources"], [])
        self.assertEqual(parsed["quantities"], [])
        self.assertEqual(parsed["confidence"], "low")
        self.assertEqual(parsed["biological_context"], "Synthetic software test only.")

    def test_all_claim_kinds_are_distinct(self):
        for kind in ("mechanism", "kinetic-law", "quantity"):
            with self.subTest(kind=kind):
                parsed = validate_ode_report(report(kind=kind), "binding")
                self.assertEqual(parsed["kind"], kind)

    def test_required_fields_and_sections_are_enforced(self):
        base = report()
        cases = {
            "wrong claim": base.replace("claim: binding", "claim: unrelated"),
            "second claim": base + "\n## ODE claim: another\n",
            "NUL": base + "\x00",
            "missing field": base.replace("**Claim:** The specified molecular states bind.\n", ""),
            "duplicate field": base + "\n**Claim:** duplicate\n",
            "blank field": base.replace("**Claim:** The specified molecular states bind.", "**Claim:**  "),
            "invalid kind": base.replace("**Kind:** mechanism", "**Kind:** arbitrary"),
            "invalid verdict": base.replace("insufficient evidence", "certain"),
            "invalid confidence": base.replace("**Confidence:** low", "**Confidence:** certain"),
            "missing section": base.replace("### Conflicts", "### Other"),
            "duplicate section": base + "\n### Conflicts\nNone.\n",
            "blank section": base.replace("Unknown.\n", "\n"),
            "out of order": base.replace("### Conflicts", "### Temporary").replace(
                "### Evidence summary", "### Conflicts"
            ).replace("### Temporary", "### Evidence summary"),
        }
        for name, content in cases.items():
            with self.subTest(name=name), self.assertRaises(ReportValidationError):
                validate_ode_report(content, "binding")

    def test_sources_and_quantities_require_unambiguous_json_arrays(self):
        cases = (
            report(sources={}),
            report(quantities={}),
            report(sources=["citation"]),
            report(quantities=["quantity"]),
            report().replace("### Sources\n[]", "### Sources\nnot JSON"),
            report().replace("### Sources\n[]", '### Sources\n[{"pmid":"123", "pmid":"456"}]'),
            report().replace("### Sources\n[]", "### Sources\n[NaN]"),
        )
        for content in cases:
            with self.subTest(content=content), self.assertRaises(ReportValidationError):
                validate_ode_report(content, "binding")

    def test_every_source_field_is_required(self):
        for key in SOURCE:
            source = copy.deepcopy(SOURCE)
            del source[key]
            with self.subTest(key=key), self.assertRaises(ReportValidationError):
                validate_ode_report(report(sources=[source]), "binding")

    def test_source_identifiers_and_details_are_validated(self):
        invalid = {
            "pmid": ["PMID 123", "", 123],
            "doi": ["https://doi.org/10.1000/test", "", 123, "10.1/test"],
            "access": ["retrieved", [], None],
            "stance": ["proven", [], None],
            "location": ["", "  ", None],
            "limitations": ["", 1],
            "context": ["", None],
            "finding": ["", []],
        }
        for key, values in invalid.items():
            for value in values:
                source = {**SOURCE, key: value}
                with self.subTest(key=key, value=value), self.assertRaises(ReportValidationError):
                    validate_ode_report(report(sources=[source]), "binding")
        with self.assertRaises(ReportValidationError):
            validate_ode_report(report(sources=[{**SOURCE, "pmid": None, "doi": None}]), "binding")
        for field in ("pmid", "doi"):
            with self.subTest(absent=field):
                validate_ode_report(report(sources=[{**SOURCE, field: None}]), "binding")

    def test_supported_claim_requires_accessible_supporting_evidence(self):
        for access in ("metadata", "abstract", "full-text", "unavailable"):
            source = {**SOURCE, "access": access}
            with self.subTest(access=access):
                parsed = validate_ode_report(report(sources=[source]), "binding")
                self.assertEqual(parsed["sources"][0]["access"], access)
                content = report(verdict="supported", sources=[source])
                if access in ("abstract", "full-text"):
                    validate_ode_report(content, "binding")
                else:
                    with self.assertRaisesRegex(ReportValidationError, "accessible supporting"):
                        validate_ode_report(content, "binding")
        for stance in ("contradicts", "context", "excluded"):
            with self.subTest(stance=stance), self.assertRaises(ReportValidationError):
                validate_ode_report(report(verdict="supported", sources=[{**SOURCE, "stance": stance}]), "binding")
        with self.assertRaises(ReportValidationError):
            validate_ode_report(report(verdict="supported"), "binding")

    def test_quantity_text_and_unknown_units_are_preserved_without_inference(self):
        for units in (None, "min^-1", "dimensionless", "units exactly as reported"):
            quantity = {**QUANTITY, "units": units}
            with self.subTest(units=units):
                parsed = validate_ode_report(report(kind="quantity", verdict="supported", sources=[SOURCE], quantities=[quantity]), "binding")
                self.assertEqual(parsed["quantities"], [quantity])
        quantity = {**QUANTITY, "source": SOURCE["doi"]}
        parsed = validate_ode_report(report(sources=[SOURCE], quantities=[quantity]), "binding")
        self.assertEqual(parsed["quantities"][0]["source"], SOURCE["doi"])

    def test_quantity_fields_units_and_source_links_are_required(self):
        for key in QUANTITY:
            quantity = copy.deepcopy(QUANTITY)
            del quantity[key]
            with self.subTest(missing=key), self.assertRaises(ReportValidationError):
                validate_ode_report(report(sources=[SOURCE], quantities=[quantity]), "binding")
        invalid = {
            "name": ["", None],
            "value": [0.1, "", None],
            "units": ["", " ", 1, []],
            "source": ["999", "", None],
            "location": ["", None],
        }
        for key, values in invalid.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ReportValidationError):
                    validate_ode_report(report(sources=[SOURCE], quantities=[{**QUANTITY, key: value}]), "binding")
        with self.assertRaisesRegex(ReportValidationError, "requires a reported quantity"):
            validate_ode_report(report(kind="quantity", verdict="supported", sources=[SOURCE]), "binding")


class ODEReportWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ode-report-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir()
        self.draft = Path(self.temp.name) / "draft.md"
        self.content = report()
        self.draft.write_text(self.content, encoding="utf-8")

    def write(self, **kwargs):
        return write_ode_report(self.root, "bio-session", "binding", self.draft, **kwargs)

    def test_exact_destination_and_readback_digest(self):
        relative = "evidence/reports/bio-session/ode/binding.md"
        result = self.write(requested_output=relative)
        self.assertEqual(result["path"], relative)
        self.assertEqual((self.root / relative).read_bytes(), self.content.encode("utf-8"))
        self.assertEqual(result["sha256"], hashlib.sha256((self.root / relative).read_bytes()).hexdigest())
        self.assertEqual(result["bytes"], len(self.content.encode("utf-8")))

    def test_existing_report_remains_unchanged(self):
        result = self.write()
        self.draft.write_text(self.content.replace("**Confidence:** low", "**Confidence:** high"))
        with self.assertRaisesRegex(ReportValidationError, "overwrite"):
            self.write()
        self.assertEqual((self.root / result["path"]).read_text(), self.content)

    def test_invalid_draft_creates_no_report(self):
        self.draft.write_text("not a report")
        with self.assertRaises(ReportValidationError):
            self.write()
        self.assertFalse((self.root / "evidence").exists())

    def test_unreadable_and_non_utf8_drafts_raise_typed_errors(self):
        self.draft.unlink()
        with self.assertRaisesRegex(ReportValidationError, "UTF-8 draft"):
            self.write()
        self.draft.write_bytes(b"\xff")
        with self.assertRaisesRegex(ReportValidationError, "UTF-8 draft"):
            self.write()

    def test_traversal_and_wrong_output_are_rejected(self):
        for session, claim in (("../other", "binding"), ("bio-session", "../other"),
                               ("/tmp/other", "binding"), ("bio-session", "other/name")):
            with self.subTest(session=session, claim=claim), self.assertRaises(ReportValidationError):
                destination(self.root, session, claim)
        for output in ("MODEL_SPEC.md", "/tmp/binding.md", "evidence/reports/bio-session/binding.md",
                       "evidence/reports/bio-session/ode/../binding.md",
                       "evidence/reports/other/ode/binding.md"):
            with self.subTest(output=output), self.assertRaises(ReportValidationError):
                self.write(requested_output=output)

    def test_symlinks_at_every_component_are_rejected(self):
        for component in ("evidence", "evidence/reports", "evidence/reports/bio-session",
                          "evidence/reports/bio-session/ode",
                          "evidence/reports/bio-session/ode/binding.md"):
            for inside in (True, False):
                with self.subTest(component=component, inside=inside):
                    root = Path(self.temp.name) / f"case-{len(list(Path(self.temp.name).iterdir()))}"
                    root.mkdir()
                    alias = root / component
                    alias.parent.mkdir(parents=True, exist_ok=True)
                    target = (root if inside else Path(self.temp.name)) / (root.name + "-target")
                    if not component.endswith(".md"):
                        target.mkdir()
                    alias.symlink_to(target, target_is_directory=not component.endswith(".md"))
                    with self.assertRaisesRegex(ReportValidationError, "symlink"):
                        write_ode_report(root, "bio-session", "binding", self.draft)
                    if component.endswith(".md"):
                        self.assertFalse(target.exists())
                    else:
                        self.assertEqual(list(target.iterdir()), [])

    def test_direct_cli_reports_validation_errors_without_traceback(self):
        # Exercise the fallback import path and its exception identity in a
        # disposable project, without letting the CLI write in the real tree.
        scripts = self.root / "scripts/codex"
        scripts.mkdir(parents=True)
        for name in ("write_literature_report.py", "ode_evidence.py"):
            shutil.copyfile(ROOT / "scripts/codex" / name, scripts / name)
        command = [sys.executable, str(scripts / "write_literature_report.py"),
                   "--session-id", "bio-session", "--claim-id", "binding",
                   "--draft-file", str(self.draft)]
        for extra in (["--source", "A"], ["--target", "B"], []):
            self.draft.write_text("invalid report")
            result = subprocess.run(command + extra, cwd=self.root, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("literature report writer:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
        self.draft.write_text(self.content)
        result = subprocess.run(command, cwd=self.root, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["claim_id"], "binding")
        repeated = subprocess.run(command, cwd=self.root, text=True, capture_output=True, timeout=10)
        self.assertEqual(repeated.returncode, 2, repeated.stderr)
        self.assertIn("overwrite", repeated.stderr)
        self.assertNotIn("Traceback", repeated.stderr)


if __name__ == "__main__":
    unittest.main()

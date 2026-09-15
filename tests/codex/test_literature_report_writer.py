from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.codex.write_literature_report import (
    ReportValidationError,
    expected_destination,
    validate_report,
    write_report,
)


VALID_REPORT = """## Edge: GAB1 -> AKT1

**Verdict:** supported
**Interaction type:** activation
**Confidence:** medium

### Evidence summary
The abstract supports the interaction in a different cellular context.

### Supporting evidence
- PMID 12345678 (DOI: 10.1000/example): abstract-only experimental evidence

### Conflicting or context-specific evidence
- None identified in the bounded search.

### Excluded references
- PMID 87654321 (DOI: none): retrieval_failed

### Open questions for researcher judgment
- Directness in the target context remains unresolved.
"""


class LiteratureReportValidationTests(unittest.TestCase):
    def test_valid_report_is_parsed(self) -> None:
        parsed = validate_report(VALID_REPORT, "GAB1", "AKT1")
        self.assertEqual(parsed.verdict, "supported")
        self.assertEqual(parsed.interaction_type, "activation")
        self.assertEqual(parsed.confidence, "medium")
        self.assertEqual(parsed.pmids, ("12345678", "87654321"))

    def test_parenthesized_doi_markdown_link_is_accepted(self) -> None:
        content = VALID_REPORT.replace(
            "10.1000/example",
            "[10.1016/S0092-8674(00)81683-9]"
            "(https://doi.org/10.1016/S0092-8674(00)81683-9)",
        )
        parsed = validate_report(content, "GAB1", "AKT1")
        self.assertEqual(parsed.pmids[0], "12345678")

    def test_malformed_reports_are_rejected(self) -> None:
        cases = {
            "missing heading": VALID_REPORT.replace("### Evidence summary\n", ""),
            "wrong edge": VALID_REPORT.replace("GAB1 -> AKT1", "GAB1 -> ERK1"),
            "invalid verdict": VALID_REPORT.replace("supported", "certain", 1),
            "invalid confidence": VALID_REPORT.replace("medium", "certain", 1),
            "missing interaction": VALID_REPORT.replace("**Interaction type:** activation\n", ""),
            "bare PMID": VALID_REPORT.replace(
                "- PMID 12345678 (DOI: 10.1000/example):",
                "- PMID 12345678:",
            ),
            "empty DOI": VALID_REPORT.replace("DOI: 10.1000/example", "DOI: "),
        }
        for name, content in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ReportValidationError):
                    validate_report(content, "GAB1", "AKT1")


class LiteratureReportWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="codex-report-writer-")
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        self.draft = Path(self.temporary.name) / "draft.md"
        self.draft.write_text(VALID_REPORT, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_writes_only_the_derived_session_scoped_filename(self) -> None:
        result = write_report(
            project_root=self.root,
            session_id="session-1",
            source="GAB1",
            target="AKT1",
            draft_path=self.draft,
        )
        target = self.root / result["path"]
        self.assertEqual(
            target,
            self.root / "evidence/reports/session-1/GAB1__AKT1.md",
        )
        self.assertEqual(target.read_text(encoding="utf-8"), VALID_REPORT)

    def test_path_traversal_is_rejected(self) -> None:
        for session, source, target in (
            ("../outside", "GAB1", "AKT1"),
            ("session", "../MODEL_SPEC", "AKT1"),
            ("session", "GAB1", "../../MODEL_SPEC"),
        ):
            with self.subTest(session=session, source=source, target=target):
                with self.assertRaises(ReportValidationError):
                    expected_destination(self.root, session, source, target)

    def test_outside_and_unexpected_output_names_are_rejected(self) -> None:
        cases = (
            "/tmp/GAB1__AKT1.md",
            "MODEL_SPEC.md",
            "evidence/reports/session-1/AKT1__GAB1.md",
            "evidence/reports/session-1/../GAB1__AKT1.md",
        )
        for output in cases:
            with self.subTest(output=output):
                with self.assertRaises(ReportValidationError):
                    expected_destination(
                        self.root,
                        "session-1",
                        "GAB1",
                        "AKT1",
                        output,
                    )

    def test_existing_report_is_never_overwritten(self) -> None:
        arguments = dict(
            project_root=self.root,
            session_id="session-1",
            source="GAB1",
            target="AKT1",
            draft_path=self.draft,
        )
        write_report(**arguments)
        self.draft.write_text(VALID_REPORT.replace("medium", "high"), encoding="utf-8")
        with self.assertRaises(ReportValidationError):
            write_report(**arguments)
        destination = self.root / "evidence/reports/session-1/GAB1__AKT1.md"
        self.assertIn("**Confidence:** medium", destination.read_text(encoding="utf-8"))

    def test_symlink_escape_is_rejected(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        reports = self.root / "evidence/reports"
        reports.mkdir(parents=True)
        try:
            (reports / "session-1").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks unavailable: {error}")

        with self.assertRaises(ReportValidationError):
            write_report(
                project_root=self.root,
                session_id="session-1",
                source="GAB1",
                target="AKT1",
                draft_path=self.draft,
            )
        self.assertFalse((outside / "GAB1__AKT1.md").exists())

    def test_dangling_file_symlink_cannot_redirect_to_another_session(self) -> None:
        session = self.root / "evidence/reports/session-1"
        other = self.root / "evidence/reports/session-2"
        session.mkdir(parents=True)
        other.mkdir()
        target = other / "GAB1__AKT1.md"
        (session / target.name).symlink_to(target)
        with self.assertRaisesRegex(ReportValidationError, "symlink"):
            write_report(project_root=self.root, session_id="session-1",
                         source="GAB1", target="AKT1", draft_path=self.draft)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()

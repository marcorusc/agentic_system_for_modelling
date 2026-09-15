#!/usr/bin/env python3
"""Validate and immutably write one session-scoped literature edge report.

The literature specialist runs read-only.  This command is the narrow write
boundary used by the Codex orchestrator after it receives a report draft.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, Sequence


IDENTIFIER = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
PMID_LINE = re.compile(r"^- PMID (?P<pmid>[0-9]{1,10}) \(DOI: (?P<doi>.+)\):(?:\s|$)")
ANY_PMID = re.compile(r"\bPMID\s+[0-9]+\b")
VERDICTS = {
    "supported",
    "contradicted",
    "context-dependent",
    "insufficient evidence",
}
INTERACTION_TYPES = {
    "activation",
    "inhibition",
    "binding",
    "transcriptional",
    "unclear",
}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
REQUIRED_SECTIONS = (
    "### Evidence summary",
    "### Supporting evidence",
    "### Conflicting or context-specific evidence",
    "### Excluded references",
    "### Open questions for researcher judgment",
)


class ReportValidationError(ValueError):
    """A draft or requested destination violates the report contract."""


@dataclass(frozen=True)
class ValidatedReport:
    source: str
    target: str
    verdict: str
    interaction_type: str
    confidence: str
    pmids: tuple[str, ...]


def _validate_identifier(value: str, label: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ReportValidationError(
            f"{label} must contain only letters, digits, '.', '_' or '-' and "
            "must not contain path separators or traversal"
        )
    return value


def _strictly_below(path: Path, directory: Path) -> bool:
    if path == directory:
        return False
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def expected_destination(
    project_root: Path,
    session_id: str,
    source: str,
    target: str,
    requested_output: str | None = None,
) -> Path:
    """Return the sole allowed output path, rejecting traversal and aliases."""

    session_id = _validate_identifier(session_id, "session ID")
    source = _validate_identifier(source, "source")
    target = _validate_identifier(target, "target")

    project = project_root.resolve(strict=True)
    reports_root = (project / "evidence" / "reports").resolve(strict=False)
    if not _strictly_below(reports_root, project):
        raise ReportValidationError("evidence/reports resolves outside the project")

    relative = Path("evidence") / "reports" / session_id / f"{source}__{target}.md"
    if requested_output is not None:
        requested = Path(requested_output)
        if requested.is_absolute() or requested != relative:
            raise ReportValidationError(
                f"output must be exactly {relative.as_posix()}"
            )

    destination = project / relative
    # Keep the lexical filename for O_EXCL/O_NOFOLLOW. Resolving it here would
    # follow a dangling symlink and create its target in a different session.
    if destination.is_symlink():
        raise ReportValidationError("report destination must not be a symlink")
    if destination.parent.resolve(strict=False) != reports_root / session_id:
        raise ReportValidationError("report destination is outside its exact session directory")
    return destination


def _field(content: str, name: str, allowed: set[str]) -> str:
    matches = re.findall(rf"^\*\*{re.escape(name)}:\*\*\s*(.+?)\s*$", content, re.MULTILINE)
    if len(matches) != 1:
        raise ReportValidationError(f"report must contain exactly one **{name}:** field")
    value = matches[0]
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ReportValidationError(f"invalid {name.lower()} {value!r}; expected one of: {choices}")
    return value


def validate_report(content: str, source: str, target: str) -> ValidatedReport:
    """Validate the Markdown contract without interpreting scientific claims."""

    _validate_identifier(source, "source")
    _validate_identifier(target, "target")
    if "\x00" in content:
        raise ReportValidationError("report contains a NUL byte")

    expected_heading = f"## Edge: {source} -> {target}"
    headings = re.findall(r"^## Edge: .+$", content, re.MULTILINE)
    if headings != [expected_heading]:
        raise ReportValidationError(
            f"report must contain exactly one heading: {expected_heading}"
        )

    positions: list[int] = []
    for heading in REQUIRED_SECTIONS:
        occurrences = [match.start() for match in re.finditer(rf"^{re.escape(heading)}$", content, re.MULTILINE)]
        if len(occurrences) != 1:
            raise ReportValidationError(f"report must contain exactly one {heading} heading")
        positions.append(occurrences[0])
    if positions != sorted(positions):
        raise ReportValidationError("required report headings are out of order")

    verdict = _field(content, "Verdict", VERDICTS)
    interaction_type = _field(content, "Interaction type", INTERACTION_TYPES)
    confidence = _field(content, "Confidence", CONFIDENCE_LEVELS)

    pmids: list[str] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if ANY_PMID.search(line):
            citation = PMID_LINE.match(line)
            if citation is None:
                raise ReportValidationError(
                    f"line {line_number}: PMID citations must use "
                    "'- PMID #### (DOI: ... or none): ...'"
                )
            doi = citation.group("doi").strip()
            if not doi:
                raise ReportValidationError(f"line {line_number}: DOI must not be empty")
            if doi.lower() != "none" and not (
                doi.startswith("10.")
                or re.fullmatch(r"\[10\.[^]]+\]\(https://doi\.org/10\..+\)", doi)
            ):
                raise ReportValidationError(
                    f"line {line_number}: DOI must be 'none', a 10.* DOI, or an https://doi.org Markdown link"
                )
            pmids.append(citation.group("pmid"))

    return ValidatedReport(
        source=source,
        target=target,
        verdict=verdict,
        interaction_type=interaction_type,
        confidence=confidence,
        pmids=tuple(pmids),
    )


def write_report(
    *,
    project_root: Path,
    session_id: str,
    source: str,
    target: str,
    draft_path: Path,
    requested_output: str | None = None,
) -> dict[str, object]:
    """Validate a draft, then create its exact destination without overwriting."""

    destination = expected_destination(
        project_root, session_id, source, target, requested_output
    )
    try:
        content = draft_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ReportValidationError(f"could not read UTF-8 draft: {error}") from error
    parsed = validate_report(content, source, target)

    reports_root = (project_root.resolve(strict=True) / "evidence" / "reports")
    reports_root.mkdir(parents=True, exist_ok=True)
    if reports_root.is_symlink() or not reports_root.resolve(strict=True).is_relative_to(
        project_root.resolve(strict=True)
    ):
        raise ReportValidationError("evidence/reports is not a safe project directory")

    session_dir = reports_root / _validate_identifier(session_id, "session ID")
    try:
        session_dir.mkdir(mode=0o755, exist_ok=True)
    except OSError as error:
        raise ReportValidationError(f"could not create report session directory: {error}") from error
    if session_dir.is_symlink() or session_dir.resolve(strict=True).parent != reports_root.resolve(strict=True):
        raise ReportValidationError("report session directory is not a direct, non-symlink child")

    # Exclusive creation enforces the immutable evidence-report contract and
    # refuses both ordinary overwrites and a symlink at the final component.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(destination, flags, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError as error:
        raise ReportValidationError(f"refusing to overwrite existing report: {destination}") from error
    except OSError as error:
        raise ReportValidationError(f"could not write report: {error}") from error

    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {
        "path": destination.relative_to(project_root.resolve(strict=True)).as_posix(),
        "sha256": digest,
        "bytes": len(content.encode("utf-8")),
        "source": parsed.source,
        "target": parsed.target,
        "verdict": parsed.verdict,
        "interaction_type": parsed.interaction_type,
        "confidence": parsed.confidence,
        "pmids": list(parsed.pmids),
    }


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--source")
    parser.add_argument("--target")
    parser.add_argument("--claim-id", help="ODE review mode; mutually exclusive with source/target")
    parser.add_argument("--draft-file", required=True, type=Path)
    parser.add_argument(
        "--output",
        help="optional assertion of the exact repository-relative output path",
    )
    return parser.parse_args(argv)


def fail(message: str) -> NoReturn:
    print(f"literature report writer: {message}", file=sys.stderr)
    raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        if arguments.claim_id:
            if arguments.source or arguments.target:
                raise ReportValidationError("--claim-id cannot be combined with --source/--target")
            try:
                from scripts.codex.ode_evidence import write_ode_report
            except ModuleNotFoundError:
                from ode_evidence import write_ode_report
            result = write_ode_report(_project_root(), arguments.session_id, arguments.claim_id,
                                      arguments.draft_file, arguments.output)
            print(json.dumps(result, sort_keys=True))
            return 0
        if not arguments.source or not arguments.target:
            raise ReportValidationError("provide --claim-id or both --source and --target")
        result = write_report(
            project_root=_project_root(),
            session_id=arguments.session_id,
            source=arguments.source,
            target=arguments.target,
            draft_path=arguments.draft_file,
            requested_output=arguments.output,
        )
    except (ReportValidationError, OSError, UnicodeError) as error:
        fail(str(error))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

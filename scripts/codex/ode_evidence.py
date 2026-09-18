"""ODE claim reports: bounded identities, explicit source access, immutable writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

try:
    from scripts.codex.write_literature_report import (
        ReportValidationError, _validate_identifier, VERDICTS, CONFIDENCE_LEVELS,
    )
except ModuleNotFoundError:
    from write_literature_report import (
        ReportValidationError, _validate_identifier, VERDICTS, CONFIDENCE_LEVELS,
    )

SECTIONS = ("Evidence summary", "Sources", "Conflicts", "Reported quantities", "Open questions")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReportValidationError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReportValidationError(f"invalid JSON constant: {value}")


def validate_ode_report(content: str, claim_id: str) -> dict:
    _validate_identifier(claim_id, "claim ID")
    if "\x00" in content:
        raise ReportValidationError("ODE report contains a NUL byte")
    headings = re.findall(r"^## ODE claim: .+$", content, re.M)
    if not content.startswith(f"## ODE claim: {claim_id}\n") or headings != [f"## ODE claim: {claim_id}"]:
        raise ReportValidationError("ODE report must start with its exact claim ID")
    fields = {}
    for name in ("Claim", "Kind", "Verdict", "Confidence", "Biological context"):
        matches = re.findall(rf"^\*\*{name}:\*\* (.+)$", content, re.M)
        if len(matches) != 1 or not matches[0].strip():
            raise ReportValidationError(f"ODE report requires one nonempty {name}")
        fields[name] = matches[0].strip()
    if fields["Kind"] not in {"mechanism", "kinetic-law", "quantity"}:
        raise ReportValidationError("invalid ODE claim kind")
    if fields["Verdict"] not in VERDICTS or fields["Confidence"] not in CONFIDENCE_LEVELS:
        raise ReportValidationError("invalid ODE verdict/confidence")
    positions = []
    bodies = {}
    for heading in SECTIONS:
        pattern = rf"^### {re.escape(heading)}\n(.*?)(?=^### |\Z)"
        matches = list(re.finditer(pattern, content, re.M | re.S))
        if len(matches) != 1 or not matches[0][1].strip():
            raise ReportValidationError(f"ODE report requires nonempty section: {heading}")
        positions.append(matches[0].start())
        bodies[heading] = matches[0][1].strip()
    if positions != sorted(positions):
        raise ReportValidationError("ODE report sections are out of order")
    # JSON records avoid ambiguous citation/quantity delimiters in free prose.
    try:
        sources = json.loads(bodies["Sources"], object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        quantities = json.loads(bodies["Reported quantities"], object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except json.JSONDecodeError as error:
        raise ReportValidationError("Sources and Reported quantities must be JSON arrays") from error
    if not isinstance(sources, list) or not isinstance(quantities, list):
        raise ReportValidationError("Sources and Reported quantities must be JSON arrays")
    for source in sources:
        if not isinstance(source, dict):
            raise ReportValidationError("source must be an object")
        for key in ("pmid", "doi", "location", "access", "limitations", "context", "finding", "stance"):
            if key not in source:
                raise ReportValidationError(f"source requires {key}")
        pmid, doi = source["pmid"], source["doi"]
        if pmid is not None and (not isinstance(pmid, str) or not re.fullmatch(r"[0-9]{1,10}", pmid)):
            raise ReportValidationError("PMID must be digits or null")
        if doi is not None and (not isinstance(doi, str) or not re.fullmatch(r"10\.\d{4,9}/\S+", doi)):
            raise ReportValidationError("DOI must be a DOI identifier or null")
        if not pmid and not doi:
            raise ReportValidationError("each source requires PMID or DOI")
        if not isinstance(source["access"], str) or source["access"] not in {"metadata", "abstract", "full-text", "unavailable"}:
            raise ReportValidationError("invalid source access level")
        if not isinstance(source["stance"], str) or source["stance"] not in {"supports", "contradicts", "context", "excluded"}:
            raise ReportValidationError("invalid evidence stance")
        for key in ("location", "limitations", "context", "finding"):
            if not isinstance(source[key], str) or not source[key].strip():
                raise ReportValidationError(f"source requires nonempty {key}")
    if fields["Verdict"] == "supported" and not any(
        s["stance"] == "supports" and s["access"] in {"abstract", "full-text"} for s in sources
    ):
        raise ReportValidationError("supported claim requires accessible supporting evidence")
    identifiers = {s[k] for s in sources for k in ("pmid", "doi") if s[k]}
    for quantity in quantities:
        if not isinstance(quantity, dict) or not {"name", "value", "units", "source", "location"} <= quantity.keys():
            raise ReportValidationError("quantity requires name, value, units, source and location")
        # Preserve reported ranges and source units verbatim; do not infer conversions.
        if any(not isinstance(quantity[k], str) or not quantity[k].strip() for k in ("name", "value", "source", "location")):
            raise ReportValidationError("reported quantity fields must be nonempty strings")
        if quantity["units"] is not None and (not isinstance(quantity["units"], str) or not quantity["units"].strip()):
            raise ReportValidationError("quantity units must be nonempty text or null")
        if quantity["source"] not in identifiers:
            raise ReportValidationError("quantity source must identify a listed source")
    if fields["Kind"] == "quantity" and fields["Verdict"] == "supported" and not quantities:
        raise ReportValidationError("supported quantity claim requires a reported quantity")
    return {"claim_id": claim_id, "claim": fields["Claim"], "kind": fields["Kind"],
            "verdict": fields["Verdict"], "confidence": fields["Confidence"],
            "biological_context": fields["Biological context"],
            "sources": sources, "quantities": quantities}


def destination(project: Path, session_id: str, claim_id: str) -> Path:
    _validate_identifier(session_id, "session ID")
    _validate_identifier(claim_id, "claim ID")
    project = project.resolve(strict=True)
    path = project / "evidence/reports" / session_id / "ode" / f"{claim_id}.md"
    for parent in (path, *path.parents):
        if parent == project:
            break
        if parent.is_symlink():
            raise ReportValidationError("ODE report path must not contain symlinks")
    return path


def write_ode_report(project: Path, session_id: str, claim_id: str, draft: Path,
                     requested_output: str | None = None) -> dict:
    path = destination(project, session_id, claim_id)
    relative = path.relative_to(project.resolve()).as_posix()
    if requested_output is not None and requested_output != relative:
        raise ReportValidationError(f"output must be exactly {relative}")
    try:
        content = draft.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ReportValidationError(f"could not read UTF-8 draft: {error}") from error
    parsed = validate_ode_report(content, claim_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ReportValidationError(f"could not create ODE report directory: {error}") from error
    destination(project, session_id, claim_id)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
    except FileExistsError as error:
        raise ReportValidationError("refusing to overwrite existing ODE report") from error
    except OSError as error:
        raise ReportValidationError(f"could not write ODE report: {error}") from error
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    try:
        recorded_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ReportValidationError(f"could not read back ODE report: {error}") from error
    if recorded_digest != digest:
        raise ReportValidationError("ODE report read-back hash mismatch")
    return {"path": relative, "sha256": digest, "bytes": len(content.encode("utf-8")), **parsed}

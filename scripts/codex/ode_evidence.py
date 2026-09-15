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


def validate_ode_report(content: str, claim_id: str) -> dict:
    _validate_identifier(claim_id, "claim ID")
    if not content.startswith(f"## ODE claim: {claim_id}\n"):
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
        sources = json.loads(bodies["Sources"])
        quantities = json.loads(bodies["Reported quantities"])
    except ValueError as error:
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
        if source["access"] not in {"metadata", "abstract", "full-text", "unavailable"}:
            raise ReportValidationError("invalid source access level")
        if source["stance"] not in {"supports", "contradicts", "context", "excluded"}:
            raise ReportValidationError("invalid evidence stance")
        for key in ("location", "limitations", "context", "finding"):
            if not isinstance(source[key], str) or not source[key].strip():
                raise ReportValidationError(f"source requires nonempty {key}")
    if fields["Verdict"] == "supported" and not any(
        s["stance"] == "supports" and s["access"] in {"abstract", "full-text"} for s in sources
    ):
        raise ReportValidationError("supported claim requires accessible supporting evidence")
    for quantity in quantities:
        if not isinstance(quantity, dict) or not {"name", "value", "units", "source", "location"} <= quantity.keys():
            raise ReportValidationError("quantity requires name, value, units, source and location")
        # Preserve reported ranges and source units verbatim; do not infer conversions.
        if any(not isinstance(quantity[k], str) or not quantity[k].strip() for k in ("name", "value", "source", "location")):
            raise ReportValidationError("reported quantity fields must be nonempty strings")
        if quantity["units"] is not None and not isinstance(quantity["units"], str):
            raise ReportValidationError("quantity units must be text or null")
        identifiers = {s[k] for s in sources for k in ("pmid", "doi") if s[k]}
        if quantity["source"] not in identifiers:
            raise ReportValidationError("quantity source must identify a listed source")
    if fields["Kind"] == "quantity" and fields["Verdict"] == "supported" and not quantities:
        raise ReportValidationError("supported quantity claim requires a reported quantity")
    return {"claim_id": claim_id, "claim": fields["Claim"], "kind": fields["Kind"],
            "verdict": fields["Verdict"], "sources": sources, "quantities": quantities}


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
    content = draft.read_text(encoding="utf-8")
    parsed = validate_ode_report(content, claim_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    destination(project, session_id, claim_id)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
    except FileExistsError as error:
        raise ReportValidationError("refusing to overwrite existing ODE report") from error
    digest = hashlib.sha256(content.encode()).hexdigest()
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ReportValidationError("ODE report read-back hash mismatch")
    return {"path": relative, "sha256": digest, **parsed}

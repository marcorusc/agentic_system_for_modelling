"""Provider-neutral edge report footer and filename contract.

Each edge report ends in exactly one fenced ``yaml`` block containing a JSON
object (JSON is a YAML 1.2 subset). Full YAML syntax is deliberately unsupported
so security hooks need no third-party parser. Strings, lists and field names must
be JSON-quoted. Required fields are verdict, interaction_type, confidence,
supporting_pmids, excluded_pmids, edge ([source, effect, target]), neko_session_id.
The footer is authoritative for citation selection; prose is cross-checked.
Existing reports are immutable; explicit revisions use .r2.md, .r3.md, etc.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
PMID = re.compile(r"[1-9][0-9]{0,9}\Z")
FIELDS = {"verdict", "interaction_type", "confidence", "supporting_pmids", "excluded_pmids", "edge", "neko_session_id"}


def _unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate footer field: {key}")
        out[key] = value
    return out


def parse_footer(content: str) -> dict:
    blocks = re.findall(r"^```yaml\n(.*?)\n```[ \t]*$", content, re.M | re.S)
    if len(blocks) != 1 or not content.rstrip().endswith("\n```"):
        raise ValueError("report must end with exactly one fenced yaml footer")
    try:
        data = json.loads(blocks[0], object_pairs_hook=_unique_object)
    except (ValueError, TypeError) as error:
        raise ValueError(f"footer must use JSON-compatible YAML: {error}") from error
    if not isinstance(data, dict) or set(data) != FIELDS:
        raise ValueError("footer must contain exactly the required evidence fields")
    enums = {'verdict': {'supported', 'contradicted', 'context-dependent', 'insufficient evidence'},
             'interaction_type': {'activation', 'inhibition', 'binding', 'transcriptional', 'unclear'},
             'confidence': {'high', 'medium', 'low'}}
    for field, choices in enums.items():
        if not isinstance(data[field], str) or data[field] not in choices:
            raise ValueError(f'invalid footer {field}')
    edge = data['edge']
    if not isinstance(edge, list) or len(edge) != 3 or any(not isinstance(value, str) or not value.strip() for value in edge):
        raise ValueError('footer edge must contain source, explicit effect, and target strings')
    if any(not SAFE.fullmatch(edge[index]) for index in (0, 2)):
        raise ValueError('unsafe footer edge identifier')
    if not isinstance(data['neko_session_id'], str) or not SAFE.fullmatch(data['neko_session_id']):
        raise ValueError('invalid footer neko_session_id')
    for field in ('supporting_pmids', 'excluded_pmids'):
        values = data[field]
        if not isinstance(values, list) or any(not isinstance(value, str) or not PMID.fullmatch(value) for value in values) or len(set(values)) != len(values):
            raise ValueError(f'{field} must contain unique PMID strings')
    if set(data['supporting_pmids']) & set(data['excluded_pmids']):
        raise ValueError('supporting and excluded PMIDs must be disjoint')
    if data['verdict'] == 'supported' and not data['supporting_pmids']:
        raise ValueError('supported verdict requires at least one supporting PMID')
    return data


def validate_footer(content: str, source: str, target: str, session_id: str | None = None) -> dict:
    data = parse_footer(content)
    edge = data["edge"]
    if (not isinstance(edge, list) or len(edge) != 3 or not all(isinstance(x, str) and x for x in edge)
            or edge[0] != source or edge[2] != target):
        raise ValueError("footer edge must match the source and target with an explicit effect")
    session = data["neko_session_id"]
    if not isinstance(session, str) or not SAFE.fullmatch(session) or (session_id is not None and session != session_id):
        raise ValueError("footer neko_session_id does not match the report session")
    for field, heading in (("verdict", "Verdict"), ("interaction_type", "Interaction type"), ("confidence", "Confidence")):
        matches = re.findall(rf"^\*\*{heading}:\*\*\s*(.+?)\s*$", content, re.M)
        if matches != [data[field]]:
            raise ValueError(f"footer {field} does not match the Markdown field")
    for field, section in (("supporting_pmids", "Supporting evidence"), ("excluded_pmids", "Excluded references")):
        values = data[field]
        if (not isinstance(values, list) or not all(isinstance(x, str) and PMID.fullmatch(x) for x in values)
                or len(set(values)) != len(values)):
            raise ValueError(f"{field} must be unique PMID strings")
        match = re.search(rf"^### {section}\n(.*?)(?=^### |^```yaml|\Z)", content, re.M | re.S)
        cited = set(re.findall(r"^- PMID ([0-9]+) ", match[1], re.M)) if match else set()
        if set(values) != cited:
            raise ValueError(f"{field} must exactly match its Markdown section")
    if set(data["supporting_pmids"]) & set(data["excluded_pmids"]):
        raise ValueError("supporting and excluded PMIDs must be disjoint")
    return data


def report_identity(project: Path, candidate: Path) -> tuple[str, str, str, bool, int]:
    """Return canonical path identity, rejecting aliases and ambiguous names."""
    relative = candidate.relative_to(project)
    parts = relative.parts
    if len(parts) not in (4, 5) or parts[:2] != ("evidence", "reports"):
        raise ValueError("invalid edge report path")
    is_candidate = len(parts) == 5
    if is_candidate and parts[3] != "candidates":
        raise ValueError("edge subdirectory must be candidates")
    name = candidate.name
    match = re.fullmatch(r"(.+)__(.+?)(?:\.r([2-9][0-9]*|1[0-9]+))?\.md", name)
    if not match:
        raise ValueError("edge filename must be source__target[.rN].md")
    source, target, revision = match.groups()
    if "__" in source or "__" in target:
        raise ValueError("edge identifiers cannot contain __")
    for value in (parts[2], source, target):
        if not SAFE.fullmatch(value):
            raise ValueError("unsafe edge report identity")
    for component in (candidate, *candidate.parents):
        if component == project:
            break
        if component.is_symlink():
            raise ValueError("edge report path must not contain symlinks")
    if candidate.resolve(strict=False) != candidate:
        raise ValueError("edge report path must be canonical")
    return parts[2], source, target, is_candidate, int(revision or 1)

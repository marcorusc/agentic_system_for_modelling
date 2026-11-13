#!/usr/bin/env python3
"""Check a seeds.json: NeKo seed genes translated from researcher-provided sources.

runs/orchestrator/<purpose>/seeds.json is the exact translation the researcher
approves when NeKo seeds come from their own sources (papers, tables, assay
results, any format under inputs/) rather than from a data-analyst proposal:

  {"schema_version": 1,
   "sources": [{"id", "path", "sha256"}, ...],
   "seeds": [{"hgnc_symbol": "KRAS", "from": [{"source": "<id>", "locator": "Table 1"}, ...]}, ...]}

Sources follow scripts/data/sources.py and are never parsed. Symbols are non-empty
and unique after stripping whitespace; each seed cites at least one declared source
and every declared source is cited. The researcher's approval is a `stage_approval`
of stage `data_seeds` whose artifact is this file and sha256, whose session_id is
<purpose>, and whose outputs equal the set of seed symbols; line 1 of the
network-curator brief is then
  DATA_INPUT {"seeds": "runs/orchestrator/<purpose>/seeds.json", "sha256": "...", "approval": "<record id>"}

CLI:
  seeds.py check SEEDS          (exit 1, one problem per line on stderr)
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path, PurePosixPath

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import state  # noqa: E402
from scripts.data import sources as user_sources  # noqa: E402
from scripts.data.common import project_root, strict_json  # noqa: E402

KEYS = ("schema_version", "sources", "seeds")
SEED_KEYS = {"hgnc_symbol", "from"}
ORCHESTRATOR = ("runs", "orchestrator")


def purpose(rel) -> str:
    """<purpose> of runs/orchestrator/<purpose>/<name>.json; ValueError for any other path."""
    form = f"seeds must be runs/orchestrator/<purpose>/<name>.json, not {rel!r}"
    if not isinstance(rel, str) or not rel or "\\" in rel or PurePosixPath(rel).as_posix() != rel:
        raise ValueError(form)
    parts = PurePosixPath(rel).parts
    if len(parts) != 4 or parts[:2] != ORCHESTRATOR or not rel.endswith(".json"):
        raise ValueError(form)
    try:
        return state.identifier(parts[2])
    except ValueError:
        raise ValueError(form) from None


def load(root: Path, rel: str) -> tuple[dict, str]:
    """The parsed seeds file and the sha256 of exactly those bytes."""
    purpose(rel)
    raw = state.artifact(Path(root), rel).read_bytes()
    data = strict_json(raw)
    if not isinstance(data, dict):
        raise ValueError("seeds file must be a JSON object")
    return data, hashlib.sha256(raw).hexdigest()


def symbols(data: dict) -> list[str]:
    """Seed symbols (stripped) in file order; call only on a checked file."""
    return [item["hgnc_symbol"].strip() for item in data["seeds"]]


def check_data(root: Path, data: dict) -> list[str]:
    errors: list[str] = []
    found = user_sources.Sources(root, errors.append)
    if set(data) != set(KEYS):
        errors.append(f"seeds keys must be exactly {', '.join(KEYS)}")
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        errors.append("schema_version must be the integer 1")
    if not isinstance(data.get("sources"), list) or not data["sources"]:
        errors.append("sources must be a non-empty list of {id, path, sha256}")
    else:
        found.declare(data["sources"], "sources")
    items = data.get("seeds")
    if not isinstance(items, list) or not items:
        errors.append("seeds must be a non-empty list of {hgnc_symbol, from}")
        items = []
    seen = set()
    for n, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != SEED_KEYS:
            errors.append(f"seeds[{n}] must have exactly hgnc_symbol and from")
            continue
        symbol = item["hgnc_symbol"]
        if not isinstance(symbol, str) or not symbol.strip():
            errors.append(f"seeds[{n}]: hgnc_symbol must be a non-empty string")
            label = f"seeds[{n}]"
        else:
            symbol = symbol.strip()
            label = f"seed {symbol}"
            if symbol in seen:
                errors.append(f"seeds[{n}]: duplicate seed {symbol}")
            seen.add(symbol)
        refs = item["from"]
        if not isinstance(refs, list) or not refs:
            errors.append(f"{label}: from must be a non-empty list of {{source, locator}}")
            continue
        for ref in refs:
            found.ref(label, ref)
    found.uncited()
    return errors


def load_and_check(root: Path, rel: str) -> tuple[dict, str, list[str]]:
    """Read the seeds file once and check exactly those bytes: (data, sha256, errors).

    An unreadable or misplaced file raises ValueError/OSError.
    """
    data, digest = load(root, rel)
    return data, digest, check_data(Path(root), data)


def check(root: Path, rel: str) -> list[str]:
    """Every problem with the seeds file, one message each; [] when it is valid."""
    try:
        data, _ = load(root, rel)
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        return [f"{rel}: {exc}"]
    return check_data(Path(root), data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check")
    c.add_argument("seeds")
    args = parser.parse_args(argv)
    errors = check(project_root().resolve(), args.seeds)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"seeds check passed: {args.seeds}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

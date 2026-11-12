#!/usr/bin/env python3
"""Offline end-to-end smoke test of the data-analyst workflow.

Run: python3 tests/integration/data_smoke.py

Works in a temporary copy of the repo. `.venv-data` is not copied: the copy gets a
real `.venv-data/` directory (copied `pyvenv.cfg`, a real `bin/` whose entries are
symlinks into the real venv), because the data guard rejects a symlinked venv (R21).
Skips (exit 0) when `.venv-data` is not installed.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
REAL_VENV = REPO / ".venv-data"

SYNTHETIC = '''\
import csv, os, sys
from pathlib import Path
import numpy as np

root = Path(os.environ["CLAUDE_PROJECT_DIR"])
sys.path.insert(0, str(root))
from scripts.data import ledger
from scripts.data.common import sha256_file, utc_now

session = Path(sys.argv[1])
rng = np.random.default_rng(1)
genes = [f"GENE{i:04d}" for i in range(1, 601)]
samples = [f"ctrl{i}" for i in range(1, 5)] + [f"treat{i}" for i in range(1, 5)]
mu = rng.uniform(50, 500, size=600)
fold = np.ones(600)
fold[:30] = 2.5
fold[30:60] = 0.4
disp = 0.1
rows = []
for g in range(600):
    row = []
    for s in range(8):
        m = mu[g] * (fold[g] if s >= 4 else 1.0)
        n = 1.0 / disp
        row.append(int(rng.negative_binomial(n, n / (n + m))))
    rows.append(row)
with (session / "outputs" / "counts.csv").open("w", newline="") as h:
    w = csv.writer(h)
    w.writerow(["gene"] + samples)
    for g, row in zip(genes, rows):
        w.writerow([g] + row)
with (session / "outputs" / "metadata.csv").open("w", newline="") as h:
    w = csv.writer(h)
    w.writerow(["sample", "condition"])
    for i, s in enumerate(samples):
        w.writerow([s, "control" if i < 4 else "treated"])
sets = {"SET_UP": genes[:30], "SET_DOWN": genes[30:60]}
for k in range(1, 19):
    sets[f"RANDOM_{k:02d}"] = list(rng.choice(genes[60:], size=30, replace=False))
gmt = session / "raw" / "sets.gmt"
gmt.write_text("".join(f"{n}\\tsynthetic\\t" + "\\t".join(v) + "\\n" for n, v in sets.items()))
ledger.append(session, {"kind": "input", "uri": "synthetic:sets.gmt", "release": "synthetic",
                        "retrieved_at": utc_now(), "sha256": sha256_file(gmt), "terms": "synthetic",
                        "path": gmt.relative_to(root).as_posix()})
'''

# Units per known numeric column. Unknown numeric columns fail loudly.
UNITS = {
    "baseMean": "normalised read counts", "log2FoldChange": "log2 ratio", "lfcSE": "log2 ratio",
    "stat": "dimensionless", "pvalue": "probability", "padj": "probability",
    "ES": "dimensionless", "NES": "dimensionless", "NOM p-val": "probability",
    "FDR q-val": "probability", "FWER p-val": "probability", "Tag %": "fraction",
    "Gene %": "fraction", "gene_set_size": "genes", "matched_size": "genes",
    "Term": None,
}
for _s in range(1, 5):
    UNITS[f"ctrl{_s}"] = UNITS[f"treat{_s}"] = "raw read counts"
UNITS["Gene_set_size"] = "genes"


def step(msg: str) -> None:
    print(f"[ok] {msg}", flush=True)


def build_outputs_index(session: Path, manifest) -> None:
    out = session / "outputs"
    entries = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        rel = path.relative_to(session).as_posix()
        if rel == "outputs/index.json":
            continue
        entry = {"path": rel, "description": f"smoke output {path.name}",
                 "identifiers": "synthetic gene IDs GENE0001-GENE0600", "units": "none"}
        if path.suffix.lower() in (".csv", ".tsv"):
            delim = "," if path.suffix.lower() == ".csv" else "\t"
            units = {}
            for col in manifest._numeric_columns(path, delim):
                unit = UNITS.get(col)
                if unit is None:
                    raise SystemExit(f"unknown numeric column {col!r} in {rel}: declare its unit")
                units[col] = unit
            entry["units"] = units
        entries.append(entry)
    (out / "index.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")


def link_venv(target: Path) -> None:
    """Reference the real venv without copying it.

    The data guard rejects a symlinked `.venv-data` directory, so `.venv-data` and its
    `bin/` are real directories whose entries are symlinks into the real venv.
    """
    (target / "bin").mkdir(parents=True)
    shutil.copy2(REAL_VENV / "pyvenv.cfg", target / "pyvenv.cfg")
    for entry in (REAL_VENV / "bin").iterdir():
        (target / "bin" / entry.name).symlink_to(entry)
    for entry in REAL_VENV.iterdir():
        if entry.name not in ("bin", "pyvenv.cfg"):
            (target / entry.name).symlink_to(entry)


def main() -> int:
    if not (REAL_VENV / "bin" / "python").exists():
        print("SKIP: .venv-data not installed")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="data-smoke-")).resolve()
    try:
        run(tmp)
    except BaseException:
        print(f"FAILED; temp dir left at {tmp}", file=sys.stderr)
        raise
    shutil.rmtree(tmp)
    return 0


def run(tmp: Path) -> None:
    root = tmp / "repo"
    shutil.copytree(REPO, root, symlinks=True, ignore=shutil.ignore_patterns(
        ".git", ".venv-*", "data-cache", "__pycache__", ".superpowers", "runs"))
    (root / "runs").mkdir(exist_ok=True)
    link_venv(root / ".venv-data")
    decisions = root / "DECISIONS.md"
    if not decisions.exists():
        decisions.write_text("# Decisions\n", encoding="utf-8")

    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root)}
    py = str(root / ".venv-data" / "bin" / "python")

    def sh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run([py, "-E", "-s", *args], cwd=root, env=env, text=True,
                              capture_output=True)
        if check and proc.returncode != 0:
            sys.stderr.write(proc.stdout + proc.stderr)
            raise SystemExit(f"command failed ({proc.returncode}): {' '.join(args)}")
        return proc

    # 1. session
    command = ".venv-data/bin/python -E -s scripts/data/session.py new --purpose smoke"
    proc = subprocess.run(command.split(), cwd=root, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    line = proc.stdout.strip().splitlines()[-1]
    assert line.startswith("Data session created: "), line
    sid = line.split()[3]
    digest = line.split("sha256=")[1].rstrip(")")
    session = root / "runs" / "data-analyst" / sid
    step(f"session created: {sid}")

    sys.path.insert(0, str(root))
    os.environ["CLAUDE_PROJECT_DIR"] = str(root)
    from scripts.capture.record_invocation import record
    from scripts.codex.validate_handoff import validate_handoff
    from scripts.data import manifest, snapshot

    # 2. DESeq2
    (session / "scripts" / "01_synthetic.py").write_text(SYNTHETIC, encoding="utf-8")
    sh(str(session / "scripts" / "01_synthetic.py"), str(session))
    de = session / "outputs" / "de"
    sh("vendor/scientific-agent-skills/pydeseq2/scripts/run_deseq2_analysis.py",
       "--counts", str(session / "outputs" / "counts.csv"),
       "--metadata", str(session / "outputs" / "metadata.csv"),
       "--design", "~condition", "--contrast", "condition", "treated", "control",
       "--output", str(de), "--plots")
    assert (de / "deseq_dataset.h5ad").is_file(), "deseq_dataset.h5ad missing"
    step("DESeq2 ran; outputs/de/deseq_dataset.h5ad exists")

    # 3. GSEA
    gsea = session / "outputs" / "gsea"
    sh("vendor/scientific-agent-skills/pathway-enrichment/scripts/run_enrichment.py", "gsea",
       "--deseq2", str(de / "deseq2_results_unshrunken.csv"),
       "--libraries", str(session / "raw" / "sets.gmt"),
       "--min-size", "15", "--permutations", "200", "--seed", "123", "--threads", "1",
       "--outdir", str(gsea))
    import csv
    with (gsea / "gsea_significant.csv").open(newline="", encoding="utf-8") as h:
        sig = list(csv.DictReader(h))
    def nes(token: str) -> list[float]:
        return [float(r["NES"]) for r in sig if token in r.get("Term", "")]
    up, down = nes("SET_UP"), nes("SET_DOWN")
    assert up and all(v > 0 for v in up), f"SET_UP not significant with NES>0: {up}"
    assert down and all(v < 0 for v in down), f"SET_DOWN not significant with NES<0: {down}"
    step(f"GSEA significant: SET_UP NES={up}, SET_DOWN NES={down}")

    # proposals + indexes + manifest
    with (de / "deseq2_results_unshrunken.csv").open(newline="", encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    first = list(rows[0].keys())[0]
    top = sorted(rows, key=lambda r: float(r["stat"]), reverse=True)[:10]
    (session / "proposals" / "P1_seed_genes.csv").write_text(
        "gene\n" + "".join(f"{r[first]}\n" for r in top), encoding="utf-8")
    (session / "proposals" / "index.json").write_text(json.dumps([
        {"id": "P1", "target_layer": "neko", "kind": "seed_genes",
         "path": "proposals/P1_seed_genes.csv", "method": "top 10 genes by DESeq2 Wald stat",
         "thresholds": {}}]), encoding="utf-8")
    build_outputs_index(session, manifest)
    (session / "report.md").write_text("# Smoke report\n\nSynthetic analysis.\n", encoding="utf-8")
    sh("scripts/data/manifest.py", "build", "--session", sid, "--skills", "pydeseq2", "pathway-enrichment")
    verify = sh("scripts/data/manifest.py", "verify", "--session", sid, check=False)
    assert verify.returncode == 0, verify.stdout + verify.stderr
    step("manifest.py verify exit 0")

    # 4. recorder (real) with a synthetic transcript
    events = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": command}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": proc.stdout.strip()}]}}]
    transcripts = tmp / "transcripts"
    transcripts.mkdir()
    tpath = transcripts / "agent-1.jsonl"
    tpath.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    record(root, {"agent_type": "data-analyst", "agent_id": "agent-1",
                  "agent_transcript_path": str(tpath)})
    integrity = json.loads((session / "integrity.json").read_text(encoding="utf-8"))
    assert integrity["passed"] is True, integrity
    step("recorder integrity passed: true")

    # 5. handoff
    base = f"runs/data-analyst/{sid}"
    artifacts = [{"path": f"{base}/{n}",
                  "sha256": hashlib.sha256((root / base / n).read_bytes()).hexdigest()}
                 for n in ("manifest.json", "report.md", "proposals/P1_seed_genes.csv")]
    handoff = {"schema_version": 1, "specialist": "data_analyst", "status": "needs_approval",
               "stage": "data", "session_id": sid, "derived_from_session_id": None,
               "actions": ["synthetic DESeq2 and GSEA"], "assumptions": [],
               "decisions_required": ["approve P1 seed genes?"], "artifacts": artifacts,
               "validation": {"checks": ["manifest verified"], "passed": True},
               "recommended_next_stage": None}
    validate_handoff(handoff, project_root=root, expected_specialist="data_analyst")
    step("validate_handoff accepted needs_approval handoff")

    # 6. negative check
    decisions.write_text("# Decisions\ntampered\n", encoding="utf-8")
    verdict = snapshot.verify_session(root, sid, digest)
    assert not verdict["passed"] and "DECISIONS.md" in verdict["changed"], verdict
    step("tampering with DECISIONS.md detected by snapshot.verify_session")
    print("DATA SMOKE PASSED")


if __name__ == "__main__":
    sys.exit(main())

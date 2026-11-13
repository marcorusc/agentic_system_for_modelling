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
import re
import shutil
import struct
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
                        "retrieved_at": utc_now(), "sha256": sha256_file(gmt), "terms": "unverified",
                        "path": gmt.relative_to(root).as_posix()})
'''

FIGURES = '''\
import csv, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

session, style = Path(sys.argv[1]), sys.argv[2]
plt.style.use(style)
figdir = session / "outputs" / "figures"
figdir.mkdir(parents=True, exist_ok=True)
with (session / "outputs" / "de" / "deseq2_results_unshrunken.csv").open(newline="") as h:
    res = [r for r in csv.DictReader(h) if r["padj"] not in ("", "NA") and r["log2FoldChange"] not in ("", "NA")]
lfc = np.array([float(r["log2FoldChange"]) for r in res])
padj = np.array([float(r["padj"]) for r in res])
nlp = -np.log10(np.clip(padj, 1e-300, None))
sig = (padj < 0.05) & (np.abs(lfc) > 1)
fig, ax = plt.subplots()
ax.scatter(lfc[~sig], nlp[~sig], s=6, color="0.6")
ax.scatter(lfc[sig], nlp[sig], s=8, color="C3")
ax.set_xlabel("log2 fold change (treated vs control)")
ax.set_ylabel("-log10 adjusted p-value")
for ext in ("png", "svg"):
    fig.savefig(figdir / f"volcano.{ext}", dpi=300)
plt.close(fig)
with (session / "outputs" / "gsea" / "gsea_significant.csv").open(newline="") as h:
    rows = list(csv.DictReader(h))
rows.sort(key=lambda r: float(r["NES"]))
fig, ax = plt.subplots()
ax.scatter([float(r["NES"]) for r in rows], range(len(rows)),
           c=[-np.log10(max(float(r["FDR q-val"]), 1e-4)) for r in rows])
ax.set_yticks(range(len(rows)), [r["Term"] for r in rows])
ax.set_xlabel("normalised enrichment score")
for ext in ("png", "svg"):
    fig.savefig(figdir / f"gsea_dotplot.{ext}", dpi=300, bbox_inches="tight")
plt.close(fig)
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


ABBREVIATIONS = {"LFC": "log2 fold change", "FDR": "false discovery rate",
                 "NES": "normalised enrichment score", "GSEA": "gene set enrichment analysis"}
FIGURE_META = {
    "volcano": {
        "title": "Volcano plot of treated vs control differential expression",
        "caption": ("Volcano plot of DESeq2 results, treated vs control (n = 4 samples per group). X axis: LFC "
                    "(log2 fold change); y axis: -log10 adjusted p-value. Red points pass FDR < 0.05 and "
                    "|LFC| > 1; grey points do not. Read it as: the further from the centre and the higher up, "
                    "the stronger and more significant the change."),
    },
    "gsea_dotplot": {
        "title": "GSEA dot plot of significant gene sets",
        "caption": ("GSEA (gene set enrichment analysis) dot plot of the significant synthetic gene sets, one dot "
                    "per set, ordered by NES (normalised enrichment score) on the x axis. Dot colour is "
                    "-log10 of the FDR q-value (clipped at 1e-4); positive NES means enrichment among genes "
                    "up in treated samples, negative NES among genes down."),
    },
}
LEDGER_URI = "synthetic:sets.gmt"

NEKO = "neko-smoke-1"
BNET_REL = f"runs/network-curator/{NEKO}/exports/inv1/model.bnet"
BNET_TEXT = "targets, factors\nEGFR, EGFR\nMAPK1, EGFR\nProliferation, MAPK1\nSurvival, MAPK1\n"
PERTURBATIONS = ("scenario_id,context,entity,entity_type,targets,effect,evidence\n"
                 "S1,LUAD,erlotinib,compound,EGFR,inhibit,GDSC\n"
                 "S2,LUAD,trametinib,compound,MAP2K1;MAP2K2,inhibit,GDSC\n")
TARGETS = ("target_id,statement,test_context,reference_context,perturbation,phenotype,expected,"
           "evidence_strength,evidence\n"
           "V1,EGFR-mutant drop larger,LUAD_EGFR,LUAD_wt,S1,viability,greater_drop,moderate,GDSC\n"
           "V2,MEK drop,LUAD_EGFR,LUAD_wt,S2,viability,greater_drop,weak,GDSC\n")


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
        if rel.startswith("outputs/figures/") and path.suffix in (".png", ".svg", ".pdf"):
            meta = FIGURE_META[path.stem]
            entry.update(meta, description=meta["title"], abbreviations=ABBREVIATIONS,
                         sources=[LEDGER_URI], script="scripts/02_figures.py")
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


def png_dpi_chunk(path: Path) -> tuple[int, int, int]:
    """Return (x pixels/metre, y pixels/metre, unit) from the PNG pHYs chunk (stdlib only)."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    pos = 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"pHYs":
            return struct.unpack(">IIB", data[pos + 8:pos + 17])
        pos += 12 + length
    raise AssertionError(f"{path.name} has no pHYs chunk")


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
    original_decisions = decisions.read_text(encoding="utf-8")

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
    from scripts.data import manifest, receive, snapshot
    from scripts.data.common import sha256_file

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

    # figures (session script, run in the data venv with the vendored publication style)
    style = root / "vendor/scientific-agent-skills/scientific-visualization/assets/publication.mplstyle"
    assert style.is_file(), style
    (session / "scripts" / "02_figures.py").write_text(FIGURES, encoding="utf-8")
    sh(str(session / "scripts" / "02_figures.py"), str(session), str(style))
    figdir = session / "outputs" / "figures"
    for name in ("volcano", "gsea_dotplot"):
        for ext in ("png", "svg"):
            assert (figdir / f"{name}.{ext}").stat().st_size > 0, f"{name}.{ext} missing or empty"
        x, y, unit = png_dpi_chunk(figdir / f"{name}.png")
        assert unit == 1 and abs(x - 11811) <= 1 and abs(y - 11811) <= 1, (name, x, y, unit)
        assert b"<svg" in (figdir / f"{name}.svg").read_bytes()
    step("figures rendered: PNG 300 dpi (pHYs) and non-empty SVG for volcano and GSEA dotplot")

    # proposals + indexes + manifest
    with (de / "deseq2_results_unshrunken.csv").open(newline="", encoding="utf-8") as h:
        rows = list(csv.DictReader(h))
    first = list(rows[0].keys())[0]
    top = sorted(rows, key=lambda r: float(r["stat"]), reverse=True)[:10]
    (session / "proposals" / "P1_seed_genes.csv").write_text(
        "hgnc_symbol,tier,evidence\n" + "".join(
            f"{r[first]},data,DESeq2 Wald stat {r['stat']}\n" for r in top), encoding="utf-8")
    (session / "proposals" / "index.json").write_text(json.dumps([
        {"id": "P1", "target_layer": "neko", "kind": "seed_genes",
         "path": "proposals/P1_seed_genes.csv", "method": "top 10 genes by DESeq2 Wald stat",
         "thresholds": {}},
        {"id": "P2", "target_layer": "maboss", "kind": "perturbations",
         "path": "proposals/P2_perturbations.csv", "method": "synthetic drug-target table",
         "thresholds": {}},
        {"id": "P3", "target_layer": "maboss", "kind": "validation_targets",
         "path": "proposals/P3_validation_targets.csv", "method": "synthetic expected responses",
         "thresholds": {}}]), encoding="utf-8")
    (session / "proposals" / "P2_perturbations.csv").write_text(PERTURBATIONS, encoding="utf-8")
    (session / "proposals" / "P3_validation_targets.csv").write_text(TARGETS, encoding="utf-8")
    build_outputs_index(session, manifest)
    sh("scripts/data/manifest.py", "build", "--session", sid, "--skills", "pydeseq2", "pathway-enrichment")
    verify = sh("scripts/data/manifest.py", "verify", "--session", sid, check=False)
    assert verify.returncode == 0, verify.stdout + verify.stderr
    step("manifest.py verify exit 0")

    # 4. handoff (mechanical, from notes)
    (session / "handoff_notes.json").write_text(json.dumps({
        "actions": ["synthetic DESeq2 and GSEA", "volcano and GSEA dotplot figures"],
        "assumptions": ["synthetic negative-binomial counts"],
        "validation_checks": ["planted SET_UP/SET_DOWN recovered by GSEA"],
        "decisions": [{"id": "D1", "question": "accept the figures as publication quality?",
                       "artifact": "outputs/figures/volcano.png"}]}), encoding="utf-8")
    hproc = sh("scripts/data/handoff.py", "build", "--session", sid, "--status", "needs_approval",
               "--notes", "handoff_notes.json")
    hline = hproc.stdout.strip().splitlines()[-1]
    hrel = f"runs/data-analyst/{sid}/handoff.json"
    assert re.fullmatch(re.escape(f"Handoff written: {hrel} sha256=") + r"[0-9a-f]{64}", hline), hline
    hdigest = hline.rsplit("sha256=", 1)[1]
    assert hdigest == sha256_file(session / "handoff.json")
    handoff = json.loads((session / "handoff.json").read_text(encoding="utf-8"))
    assert handoff["status"] == "needs_approval"
    assert [d["id"] for d in handoff["decisions_required"]] == ["P1", "P2", "P3", "D1"], handoff["decisions_required"]
    step("handoff.py build wrote handoff.json")

    # 5. recorder (real) with a synthetic transcript ending in SubagentHandback
    report_text = (
        "# Smoke report\n\n## Question and scope\n\nSynthetic analysis.\n\n"
        f"## Sources\n\n- sets.gmt ({LEDGER_URI}), release synthetic; feeds both figures.\n\n"
        "## Methods\n\nDESeq2 then GSEA (Fig. 1, `volcano.png`; Fig. 2, `gsea_dotplot.png`).\n\n"
        "## Results\n\nPlanted sets recovered.\n\n"
        "## Figures\n\n"
        "- `outputs/figures/volcano.png` (and .svg): " + FIGURE_META["volcano"]["title"] + ". "
        + FIGURE_META["volcano"]["caption"] + "\n"
        "- `outputs/figures/gsea_dotplot.png` (and .svg): " + FIGURE_META["gsea_dotplot"]["title"] + ". "
        + FIGURE_META["gsea_dotplot"]["caption"] + "\n\n"
        "## Abbreviations\n\n" + "".join(f"- {k}: {v}\n" for k, v in ABBREVIATIONS.items())
        + "\n## Limitations\n\nSynthetic data.\n\n## Proposals and decisions\n\nP1, D1.\n\n"
        f"Handoff: {hrel} sha256={hdigest}")
    events = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": command}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": proc.stdout.strip()}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t2", "name": "SubagentHandback",
             "input": {"message": report_text}}]}}]
    agent_id = "agent-1"
    # The hook never firing leaves runs/index.json and its lock exactly as before the
    # capture (they are snapshot-protected), so remember their pre-record state.
    shared = [root / "runs" / "index.json", root / "runs" / ".index.capture.lock"]
    before = {f: (f.read_bytes() if f.exists() else None) for f in shared}
    tpath = tmp / f"{agent_id}.jsonl"
    tpath.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    record(root, {"agent_type": "data-analyst", "agent_id": agent_id,
                  "agent_transcript_path": str(tpath)})
    integrity = json.loads((session / "integrity.json").read_text(encoding="utf-8"))
    assert integrity["passed"] is True, integrity
    validate_handoff(handoff, project_root=root, expected_specialist="data_analyst",
                     expected_session_id=sid)
    final_report = session / "invocation" / agent_id / "final_report.md"
    assert (session / "report.md").read_bytes() == final_report.read_bytes()
    assert final_report.read_text(encoding="utf-8").rstrip().endswith(f"Handoff: {hrel} sha256={hdigest}")
    step("recorder integrity passed: true; validate_handoff accepted handoff; report.md written from SubagentHandback")

    # 5b. simulate the hook never firing, then recover with receive.py
    (session / "integrity.json").unlink()
    shutil.rmtree(session / "invocation")
    (session / "report.md").unlink()
    index = json.loads((root / "runs" / "index.json").read_text(encoding="utf-8"))
    assert any(r.get("capture_path") == f"runs/data-analyst/{sid}/invocation/{agent_id}"
               for r in index["runs"]), index
    for f, content in before.items():  # drop the capture's index entry
        if content is None:
            f.unlink(missing_ok=True)
        else:
            f.write_bytes(content)
    troot = tmp / "transcripts"
    tdir = troot / receive.project_slug(root) / "uuid-1" / "subagents"
    tdir.mkdir(parents=True)
    shutil.copy2(tpath, tdir / f"agent-{agent_id}.jsonl")
    rproc = subprocess.run(
        ["python3", "scripts/data/receive.py", "--session", sid, "--agent-id", agent_id,
         "--transcript-root", str(troot)], cwd=root, env=env, text=True, capture_output=True)
    assert rproc.returncode == 0, rproc.stdout + rproc.stderr
    assert rproc.stdout.strip().splitlines()[-1] == f"RECEIVED {sid} OK", rproc.stdout
    assert (session / "report.md").is_file()
    assert (session / "report.md").read_bytes() == final_report.read_bytes()
    integrity = json.loads((session / "integrity.json").read_text(encoding="utf-8"))
    assert integrity["passed"] is True, integrity
    step("receive.py recovered the missing capture: RECEIVED OK, report.md == final_report.md")

    # 6. negative check
    decisions.write_text("# Decisions\ntampered\n", encoding="utf-8")
    verdict = snapshot.verify_session(root, sid, digest)
    assert not verdict["passed"] and "DECISIONS.md" in verdict["changed"], verdict
    step("tampering with DECISIONS.md detected by snapshot.verify_session")

    # 7. data -> NeKo -> MaBoSS handoffs (the orchestrator procedure of docs/data-workflow.md)
    from scripts import gate
    decisions.write_text(original_decisions, encoding="utf-8")  # undo the deliberate tamper

    def write_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def sha_of(rel: str) -> str:
        return sha256_file(root / rel)

    def record_state(record: dict) -> None:
        file = tmp / f"{record['id']}.json"
        write_json(file, record)
        sh("scripts/state.py", "record", "--input", str(file))

    base = f"runs/data-analyst/{sid}"
    record_state({"id": "dec-data-1", "kind": "stage_approval", "stage": "data", "session_id": sid,
                  "outputs": ["P1", "P2", "P3"],
                  "artifact": {"path": f"{base}/handoff.json", "sha256": sha_of(f"{base}/handoff.json")},
                  "approved_by": "researcher", "authorization": "researcher: data approved"})
    seeds = f"{base}/proposals/P1_seed_genes.csv"
    neko_line = "DATA_INPUT " + json.dumps({"data_session": sid, "proposals": {"P1": sha_of(seeds)}})
    neko_task = f"{neko_line}\nBuild the network from the seed file {seeds} (hgnc_symbol column)."
    result = gate.check_data_input(root, "network_curator", neko_task)
    assert result["data_session"] == sid and result["approval_id"] == "dec-data-1", result
    bad_neko = neko_task.replace(sha_of(seeds), "0" * 64)
    try:
        gate.check_data_input(root, "network_curator", bad_neko)
    except ValueError as exc:
        assert "sha256" in str(exc), exc
    else:
        raise AssertionError("NeKo brief with a wrong proposal hash was accepted")
    step("data approval recorded; network-curator DATA_INPUT accepted, wrong proposal hash refused")

    bnet = root / BNET_REL
    bnet.parent.mkdir(parents=True)
    bnet.write_text(BNET_TEXT, encoding="utf-8")
    mapping_rel = "runs/orchestrator/luad/mapping.json"
    sh("scripts/data/mapping.py", "draft", "--purpose", "luad", "--data",
       f"{sid}:P2:dec-data-1", f"{sid}:P3:dec-data-1", "--network", f"{NEKO}:{BNET_REL}")
    skeleton = sh("scripts/data/mapping.py", "check", mapping_rel, check=False)
    assert skeleton.returncode == 1 and "TODO" in skeleton.stderr, skeleton.stderr
    data = json.loads((root / mapping_rel).read_text(encoding="utf-8"))
    data["contexts"] = {"LUAD_EGFR": [{"node": "EGFR", "state": 1}], "LUAD_wt": []}
    data["perturbations"] = [{"id": "S1", "from": {"proposal": "P2", "row": "S1"},
                              "model": [{"node": "EGFR", "state": 0}], "note": "erlotinib -> EGFR off"}]
    data["readouts"] = [{"phenotype": "viability", "nodes": ["Proliferation", "Survival"]}]
    data["criteria"] = [{"criterion_id": "V1", "from": {"proposal": "P3", "row": "V1"},
                         "method": "scenario_contrast",
                         "test": {"context": "LUAD_EGFR", "perturbation": "S1"},
                         "reference": {"context": "LUAD_wt", "perturbation": "S1"},
                         "options": {"readouts": ["Proliferation"], "margin": 0.05, "combine": "all",
                                     "statistic": "tail_mean", "tail_points": 2}}]
    data["unmapped"] = [{"from": {"proposal": "P2", "row": "S2"}, "reason": "MEK is not a model node"},
                        {"from": {"proposal": "P3", "row": "V2"}, "reason": "depends on unmapped S2"}]
    write_json(root / mapping_rel, data)
    checked = sh("scripts/data/mapping.py", "check", mapping_rel, check=False)
    assert checked.returncode == 0 and not checked.stderr, checked.stdout + checked.stderr
    record_state({"id": "dec-map-1", "kind": "stage_approval", "stage": "data_mapping", "session_id": NEKO,
                  "outputs": ["S1", "V1"],
                  "artifact": {"path": mapping_rel, "sha256": sha_of(mapping_rel)},
                  "approved_by": "researcher", "authorization": "researcher: mapping ok"})
    step("mapping.py draft, completed mapping passes check, data_mapping approval recorded")

    stage_gate = "STAGE_GATE " + json.dumps({"upstream_session_id": NEKO, "outputs": ["Proliferation", "Survival"]})
    maboss_line = "DATA_INPUT " + json.dumps({"mapping": mapping_rel, "sha256": sha_of(mapping_rel),
                                              "approval": "dec-map-1"})
    maboss_task = f"{stage_gate}\n{maboss_line}\nSimulate exactly the mapping's scenarios."
    result = gate.check_data_input(root, "boolean_dynamics_modeler", maboss_task)
    assert result, result
    bad_maboss = maboss_task.replace(sha_of(mapping_rel), "0" * 64)
    try:
        gate.check_data_input(root, "boolean_dynamics_modeler", bad_maboss)
    except ValueError as exc:
        assert "sha256" in str(exc), exc
    else:
        raise AssertionError("MaBoSS brief with a wrong mapping hash was accepted")
    step("boolean-dynamics-modeler DATA_INPUT accepted, wrong mapping hash refused")

    traj = "runs/boolean-dynamics-modeler/smoke-1"
    levels = {"test_control": 0.8, "test_perturbed": 0.2, "reference_control": 0.8, "reference_perturbed": 0.7}
    scenarios = {"test_control": ("LUAD_EGFR", None), "test_perturbed": ("LUAD_EGFR", "S1"),
                 "reference_control": ("LUAD_wt", None), "reference_perturbed": ("LUAD_wt", "S1")}
    runs = []
    for role, (context, perturbation) in scenarios.items():
        rel = f"{traj}/{role}.csv"
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("Time,Proliferation,Survival\n" + "".join(
            f"{t},{levels[role]},0.5\n" for t in (0, 1, 2, 3)), encoding="utf-8")
        runs.append({"context": context, "perturbation": perturbation, "trajectory": rel})
    write_json(root / "runs/orchestrator/luad/runs.json", {"runs": runs})
    sh("scripts/data/mapping.py", "criteria", mapping_rel, "--runs", "runs/orchestrator/luad/runs.json",
       "--merge-into", "VALIDATION_CRITERIA.yaml")
    merged = json.loads((root / "VALIDATION_CRITERIA.yaml").read_text(encoding="utf-8"))
    assert [c["criterion_id"] for c in merged["criteria"]] == ["V1"], merged
    assert merged["criteria"][0]["inputs"] == [r["trajectory"] for r in runs], merged
    step("mapping.py criteria merged scenario_contrast V1 into VALIDATION_CRITERIA.yaml")

    evaluation = json.loads(sh("scripts/validate/evaluate.py", "--criteria", "VALIDATION_CRITERIA.yaml").stdout)
    outcome = {r["criterion_id"]: r["status"] for r in evaluation["results"]}
    assert outcome == {"V1": "passed"}, evaluation
    step("evaluate.py: scenario_contrast V1 passed (EGFR-off drop larger in the test context)")
    print("DATA SMOKE PASSED")


if __name__ == "__main__":
    sys.exit(main())

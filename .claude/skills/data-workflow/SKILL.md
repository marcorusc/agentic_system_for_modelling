---
name: data-workflow
description: Operational guide for the data-analyst specialist (sessions, command allowlist, vendored guide index, output and proposal templates). Preloaded into data-analyst; the main session delegates data work to that agent instead of loading this skill.
---

# Data workflow

Preloaded into `data-analyst`. The main session never loads this skill and never runs
the commands below; it delegates to `data-analyst`.

## 1. Session lifecycle

1. Create exactly one session per invocation (plain ASCII purpose, none of
   `& $ | ; < > \` backslash`):

   `.venv-data/bin/python -E -s scripts/data/session.py new --purpose "short ascii purpose" [--derived-from <earlier-id>]`

   The last stdout line is `Data session created: <id> (snapshot sha256=<hex>)`. That
   `<id>` is the active session. Never run `session.py new` a second time.
2. Work inside `runs/data-analyst/<id>/` (`scripts/`, `raw/`, `outputs/`, `proposals/`).
3. Register researcher-supplied files:
   `.venv-data/bin/python -E -s scripts/data/fetch.py --session <id> --input inputs/<file> --release "<text>"`
4. Download a plain URL (no query string):
   `.venv-data/bin/python -E -s scripts/data/fetch.py --session <id> --url <URL> --name <file> --release "<release>" [--terms "<terms>"] [--expect tabular] [--max-bytes N]`

   `--expect` takes one of `binary` (default), `tabular` or `json`; pass exactly one
   value, for example `--expect tabular`.
5. Finalize and verify:
   `.venv-data/bin/python -E -s scripts/data/manifest.py build --session <id> --skills <guide> ...`
   `.venv-data/bin/python -E -s scripts/data/manifest.py verify --session <id>`
6. Write `report.md`, then return the handoff envelope (see the agent definition).

If `.venv-data` is missing, return `blocked` with remediation `python3 scripts/setup.py --with-data`.

## 2. Command rules

Only these Bash forms are accepted by the guard:

- Interpreter form is exactly `.venv-data/bin/python -E -s <script> [args]`.
- Allowed scripts: `runs/data-analyst/<id>/scripts/*.py`,
  `vendor/scientific-agent-skills/*/scripts/*.py` (invoked by path, never copied), and
  `scripts/data/session.py`, `scripts/data/fetch.py`, `scripts/data/manifest.py`.
  Other `scripts/data` modules (`ledger`, `common`, ...) are imported from saved scripts.
- Plain `ls` and `head` inside the repository.
- `fetch.py` and `manifest.py` must always pass `--session <active>`.
- The command line may not contain `;` `|` `&` `<` `>` `$` backticks, backslash, newlines
  or non-ASCII; unquoted globs, braces and `~` are rejected. URLs with `?` or `&` cannot
  be passed on the command line: fetch them from a saved script with
  `fetch.download(session_dir, url=..., name=..., release=..., terms=..., expect=...)`,
  and record API calls with `ledger.record_api(...)`.
- Write only inside `runs/data-analyst/<id>/`. Never write `identity.json`,
  `manifest.json`, `integrity.json`, `sources.jsonl` or anything under `invocation/`.
- Never modify a recorded source (`raw/` files, `data-cache/`, `inputs/`): `manifest.py
  verify` re-hashes every ledgered source path. Write derived data under `outputs/`.
- Vendored scripts: always pass explicit output paths inside
  `runs/data-analyst/<id>/outputs/...`. Defaults write relative to the repository root:
  `pydeseq2` `--output` (default `results`), `pathway-enrichment` `--outdir` (default
  `enrichment_results`), `bulk-rnaseq` `--output-dir` (default `counts`). For example
  `--output runs/data-analyst/<id>/outputs/de`. Never rely on a default output path.
- Every analysis is a saved script, then executed. Script header template:

```python
#!/usr/bin/env python3
import sys
from pathlib import Path

SESSION = Path(__file__).resolve().parents[1]   # runs/data-analyst/<id>
ROOT = Path(__file__).resolve().parents[4]      # repository root
sys.path.insert(0, str(ROOT))

from scripts.data import fetch, ledger  # noqa: E402
```

## 3. Task to vendored-guide index

Read the guide's `SKILL.md` first, then only the references you need. Paths are under
`vendor/scientific-agent-skills/`.

| Task | Read |
|---|---|
| DepMap dependencies, co-essentiality | `depmap/SKILL.md`, `depmap/references/dependency_analysis.md` |
| TCGA / GDC, cBioPortal cohorts | `database-lookup/SKILL.md`, `database-lookup/references/tcga-gdc.md`, `database-lookup/references/cbioportal.md` |
| GEO, PRIDE, Open Targets, other databases | `database-lookup/SKILL.md`, `database-lookup/references/{geo,pride,opentargets,database_selection_guide,retrieval-contract}.md` |
| Gene lookup, sequences, gget modules | `gget/SKILL.md`, `gget/references/` |
| Bulk RNA-seq design, QC, counts | `bulk-rnaseq/SKILL.md`, `bulk-rnaseq/references/` |
| Differential expression | `pydeseq2/SKILL.md`, `pydeseq2/references/` |
| Enrichment, gene sets | `pathway-enrichment/SKILL.md`, `pathway-enrichment/references/` |
| Microscopy features | `cellprofiler/SKILL.md`, `cellprofiler/references/runtime-and-qc.md` (needs the optional CellProfiler install; otherwise `blocked`) |
| Statistical tests, effect sizes | `statistical-analysis/SKILL.md`, `statistical-analysis/references/` |
| Machine learning, clustering | `scikit-learn/SKILL.md`, `scikit-learn/references/` |
| Units, uncertainty, plausibility | `uncertainty-and-units/SKILL.md`, `uncertainty-and-units/references/` |

## 4. DepMap access notes

- The DepMap portal catalogue may return a verification page instead of data. Do not
  scrape around it. Ask the researcher to download the file into `inputs/` and register
  it with `fetch.py --input`; it is then referenced by hash.
- For single-gene questions, the Open Targets `depMapEssentiality` GraphQL field may be
  used (see `database-lookup/references/opentargets.md`).

## 5. Scientific rules

- Network scope: only documented database APIs and download endpoints named in the
  vendored guides, or URLs the researcher supplied. No general web search or scraping.
- Never infer units or identifiers; never invent values; record every source release.
- Associations are not mechanisms. Candidate edges go to the orchestrator for
  `literature-reviewer`.
- Every data-to-model choice is a proposal, never a decision. Report limitations.

## 6. Templates

Both index files are a bare JSON list of objects (no wrapping object).

`outputs/index.json` (one entry per output; units per numeric column or `"dimensionless"`;
identifiers type or `"none"`):

```json
[{"path": "outputs/de.csv", "description": "DESeq2 results",
  "units": {"log2FoldChange": "log2 ratio", "padj": "dimensionless"},
  "identifiers": "HGNC symbol"}]
```

`proposals/index.json`:

```json
[{"id": "P1", "target_layer": "neko", "kind": "seed_genes",
  "path": "proposals/P1_seed_genes.csv", "method": "what was done",
  "thresholds": {"padj": 0.05}, "status": "proposed"}]
```

`target_layer` is one of `spec`, `neko`, `maboss`, `biomass`, `physicell`; `kind` is one
of `seed_genes`, `initial_states`, `mutations`, `validation_targets`, `parameters`,
`time_course`. Use exactly one value each.

`report.md` headings:

```markdown
# <title>
## 1. Question and scope
## 2. Sources (release, date, terms)
## 3. Methods (scripts, parameters, seeds, vendored guides used)
## 4. Results
## 5. Limitations
## 6. Proposals and decisions required from the researcher
```

## 7. Citation reminder

Pass every vendored guide that informed the analysis to `manifest.py build --skills`
(for example `--skills pydeseq2 pathway-enrichment`) and list them in the report Methods,
so the analyses can cite K-Dense scientific-agent-skills (see `THIRD_PARTY_NOTICES.md`).

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
6. Write `handoff_notes.json` in the session root (schema below), then build the handoff:
   `.venv-data/bin/python -E -s scripts/data/handoff.py build --session <id> --status <needs_approval|completed|blocked|failed> --notes handoff_notes.json`
   The last stdout line is `Handoff written: runs/data-analyst/<id>/handoff.json sha256=<hex>`.
   Run it last: rebuilding `handoff.json` after you copy that line makes the orchestrator's
   `receive.py` fail.
7. Final message: the human-readable report (headings in section 7), whose last line is
   exactly `Handoff: runs/data-analyst/<id>/handoff.json sha256=<64hex>`. The recorder saves
   that message as `report.md`; do not write `report.md` or `handoff.json` yourself and
   never hand-write a JSON envelope.

Lifecycle summary: `manifest.py build` -> `manifest.py verify` -> write
`handoff_notes.json` -> `handoff.py build` -> final message with the report and the
exact `Handoff:` line.

`handoff_notes.json` (unknown keys are rejected; `artifact` is optional):

```json
{"actions": ["..."], "assumptions": ["..."], "validation_checks": ["..."],
 "decisions": [{"id": "D1", "question": "...", "artifact": "outputs/x.csv"}],
 "blocked": [{"what": "...", "why": "...", "remediation": "..."}]}
```

`handoff.py` generates the envelope fields, the artifact hashes and one decision per
manifest proposal. Status rules (the script refuses violations):

| Situation | Status |
|---|---|
| Any proposal, including partial results with blocked parts | `needs_approval`; blocked parts are decision items |
| Outputs only, no proposals, nothing blocked | `completed` |
| No outputs and no proposals | `blocked`; needs at least one `blocked` item or decision (the reason) |
| Verification failed or a script crashed | `failed` |

No session (for example `.venv-data` is missing, so `session.py new` cannot run): there is
nothing to hand off. Your final message states `blocked`, the reason and the remediation
(`python3 scripts/setup.py --with-data`) and has no `Handoff:` line; the orchestrator
skips `receive.py` and relays the reason.

## 2. Command rules

Only these Bash forms are accepted by the guard:

- Interpreter form is exactly `.venv-data/bin/python -E -s <script> [args]`.
- Allowed scripts: `runs/data-analyst/<id>/scripts/*.py`,
  `vendor/scientific-agent-skills/*/scripts/*.py` (invoked by path, never copied), and
  `scripts/data/session.py`, `scripts/data/fetch.py`, `scripts/data/manifest.py`,
  `scripts/data/handoff.py`.
  Other `scripts/data` modules (`ledger`, `common`, ...) are imported from saved scripts.
- Plain `ls` and `head` inside the repository.
- To search files (including the vendored guides) use the Grep, Glob and Read tools.
  Shell `grep`, `find`, `cat` and similar are not allowed.
- Write every command on a single line. Never use `\` line continuations; put long
  logic in a saved script instead.
- `fetch.py`, `manifest.py` and `handoff.py` must always pass `--session <active>`.
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
| Publication figures, style, palettes | `scientific-visualization/SKILL.md`, `scientific-visualization/references/`, `scientific-visualization/assets/` |
| Statistical plots (distributions, heatmaps, categorical) | `seaborn/SKILL.md`, `seaborn/references/` |

## 4. Data-source notes

### DepMap

- The DepMap portal catalogue may return a verification page instead of data. Do not
  scrape around it. Ask the researcher to download the file into `inputs/` and register
  it with `fetch.py --input`; it is then referenced by hash.
- For single-gene questions, the Open Targets `depMapEssentiality` GraphQL field may be
  used (see `database-lookup/references/opentargets.md`).

### cBioPortal datahub

The datahub git-LFS / S3 download can fail (LFS pointer files or S3 errors instead of
data). Do not retry blindly. Fall back to the cBioPortal API and reconcile record
counts: compare the number of samples/patients/mutations retrieved against the study
summary count and report any discrepancy in the Sources and Limitations sections.

### Source documents (PDF, Excel)

Units, concentrations and assay durations must come from the source's own documentation,
never from memory. `.venv-data` includes `pypdf` (read PDF descriptions, e.g. GDSC
release notes) and `openpyxl` (`pandas.read_excel` for `.xlsx` releases, e.g. GDSC or
DepMap). Read them from a saved script, register each document in the ledger like any
other source, and quote the exact unit text in the report.

### Ledger `terms`

The `terms` value in `sources.jsonl` must be `""`, `"unverified"`, or `"quoted: "`
followed by text copied verbatim from the source's own terms page. Never paraphrase or
invent licence terms; use `"unverified"` when you did not read them.

## 5. Figures

- **Location and format:** figures go in `outputs/figures/`, as PNG (300 dpi) plus SVG. Each file is listed in `outputs/index.json` with `units: "none"` and an `identifiers` value, plus the figure metadata below. `manifest.py verify` rejects a figure (an indexed `.png`/`.svg`/`.pdf` under `outputs/figures/`) that lacks it, and `receive.py` rejects a report that does not name every figure.
- **Figure metadata (required):** `title` (non-empty); `caption` (at least 80 characters: axes, colours and markers, n per group, test, thresholds, how to read it; never a one-liner); `abbreviations` (object abbreviation -> expansion, `{}` only if the figure uses none); `sources` (non-empty list of `uri` values copied verbatim from `sources.jsonl`; a figure may list several); `script` (session-relative path of the existing file under `scripts/` that made it). Keep `description` (set it to the title). A PNG/SVG pair may share identical metadata.
- **Readable figures:** axis labels spell out the quantity and unit; every abbreviation shown in a figure is defined in its `abbreviations` or avoided (for example write "log2 fold change", not "LFC", unless defined).
- **In the report:** Figures section (one entry per figure: path, title, full description, key observation, data source), an Abbreviations glossary, and inline citations in Methods and Results such as "differential expression (Fig. 4, `fig04_volcano_luad.png`)". See section 7.
- **Style:** use `vendor/scientific-agent-skills/scientific-visualization/assets/publication.mplstyle` and its colour-blind-safe palettes. Run `palette_audit.py` on custom palettes.
- **The vendored skill's run instructions do not apply here.** Its `uv run --isolated ...`
  commands, running from the skill directory, and `Path.cwd()` as the skill root (in
  `references/matplotlib_examples.md`) are all refused by the guard or resolve wrongly:
  `uv` and `cd` are not allowed, and every command runs from the repository root. Read
  its guidance; run figures as below.
- **How to make a figure:** save a script as `runs/data-analyst/<id>/scripts/NN_figures.py`
  and run `.venv-data/bin/python -E -s runs/data-analyst/<id>/scripts/NN_figures.py`.
  Reach vendored assets and helper modules by repository-relative path through
  `sys.path`, never by copying them:

  ```python
  #!/usr/bin/env python3
  import sys
  from pathlib import Path

  SESSION = Path(__file__).resolve().parents[1]   # runs/data-analyst/<id>
  ROOT = Path(__file__).resolve().parents[4]      # repository root
  VIS = ROOT / "vendor" / "scientific-agent-skills" / "scientific-visualization"
  sys.path[:0] = [str(VIS / "assets"), str(VIS / "scripts")]

  import matplotlib  # noqa: E402
  matplotlib.use("Agg")  # headless, no display
  import matplotlib.pyplot as plt  # noqa: E402
  from color_palettes import OKABE_ITO_ON_WHITE  # noqa: E402

  plt.style.use(VIS / "assets" / "publication.mplstyle")
  figdir = SESSION / "outputs" / "figures"
  figdir.mkdir(parents=True, exist_ok=True)
  fig, ax = plt.subplots()
  ...  # plot with OKABE_ITO_ON_WHITE; label axes with units and n per group
  for ext in ("png", "svg"):
      fig.savefig(figdir / f"volcano.{ext}", dpi=300)
  plt.close(fig)
  ```

  Then list each file in `outputs/index.json` with the figure metadata (see section 7).
- **Palette audit** (bundled palette, or repeat `--color` with a quoted hex per colour):

  `.venv-data/bin/python -E -s vendor/scientific-agent-skills/scientific-visualization/scripts/palette_audit.py --palette okabe_ito_on_white --role graphical --output runs/data-analyst/<id>/outputs/figures/palette_audit.json`

  `--color "#0072B2" --color "#D55E00"` replaces `--palette`; `--list-palettes` prints the
  bundled names. It refuses to overwrite an existing `--output` unless `--force` is given.
  Index `palette_audit.json` in `outputs/index.json` too: `manifest.py verify` fails on any
  unindexed file under `outputs/`.
  Report `contrast_screen.review_count` and `grayscale_screen.review_count`; a review
  finding means adding redundant encodings (markers, line styles, direct labels) or
  stating it under Limitations. `--fail-on background|grayscale|any` makes it exit 1 on
  such findings.
- **Required figure sets** (produce those that apply):

  | Analysis | Figures |
  |---|---|
  | Cohort / mutation | Alteration landscape (genes × samples or frequency bars by cohort); co-occurrence / mutual-exclusivity heatmap with q-values |
  | Expression QC | Library sizes; PCA coloured by condition/batch |
  | Differential expression | Volcano (labelled top genes, thresholds drawn); MA plot; heatmap of top genes (z-scored) |
  | Enrichment | GSEA dot plot (NES, q); running-score plots for sets cited in the report |
  | DepMap / dependencies | Gene-effect distributions by stratum (violin or box plus points); dependency ranking |
  | Proposal summary | One figure per proposal showing the evidence behind each seed or target (e.g. per-gene evidence tiles) |

- **Honesty rules:** state n per group in the figure or caption; never truncate axes without marking it; show uncertainty where it exists.

## 6. Scientific rules

- Network scope: only documented database APIs and download endpoints named in the
  vendored guides, or URLs the researcher supplied. No general web search or scraping.
- Never infer units or identifiers; never invent values; record every source release.
- Associations are not mechanisms. Candidate edges go to the orchestrator for
  `literature-reviewer`.
- Every data-to-model choice is a proposal, never a decision. Report limitations.

## 7. Templates

Both index files are a bare JSON list of objects (no wrapping object).

`outputs/index.json` (one entry per output; units per numeric column or `"dimensionless"`;
identifiers type or `"none"`):

```json
[{"path": "outputs/de.csv", "description": "DESeq2 results",
  "units": {"log2FoldChange": "log2 ratio", "padj": "dimensionless"},
  "identifiers": "HGNC symbol"}]
```

A figure entry (path under `outputs/figures/`, suffix `.png`, `.svg` or `.pdf`) also needs
`title`, `caption` (>= 80 characters), `abbreviations`, `sources` and `script`:

```json
{"path": "outputs/figures/fig04_volcano_luad.png", "description": "Volcano plot, LUAD tumour vs normal",
 "units": "none", "identifiers": "HGNC symbol",
 "title": "Volcano plot, LUAD tumour vs normal",
 "caption": "Volcano plot of differential expression, tumour (n = 40) vs normal (n = 40). X axis: log2 fold change; y axis: -log10 adjusted p-value; red points pass FDR < 0.05 and |LFC| > 1. Top genes are labelled.",
 "abbreviations": {"LUAD": "lung adenocarcinoma", "LFC": "log2 fold change", "FDR": "false discovery rate"},
 "sources": ["https://example.org/api?release=v1"],
 "script": "scripts/02_figures.py"}
```

`proposals/index.json`:

```json
[{"id": "P1", "target_layer": "neko", "kind": "seed_genes",
  "path": "proposals/P1_seed_genes.csv", "method": "what was done",
  "thresholds": {"padj": 0.05}, "status": "proposed"}]
```

`target_layer` is one of `spec`, `neko`, `maboss`, `biomass`, `physicell`; `kind` is one
of `seed_genes`, `initial_states`, `perturbations`, `validation_targets`, `parameters`,
`time_course`. Use exactly one value each. Proposal ids are `P1`, `P2`, ... (`^P\d+$`;
`P2b` is rejected), and each proposal file is named after its id (`P3_<what>.csv`).

### Proposal schemas

`seed_genes`, `perturbations` and `validation_targets` proposals must be CSV/TSV tables.
`manifest.py verify` requires every column below, non-empty on every row. Extra columns
(your statistics) are allowed. Column names must be unique, the table needs at least one
data row, and enum values are exact, lowercase, as listed (no case folding). `mutations` is no longer a kind; use `perturbations`.

`seed_genes` (`target_layer` `neko`):

| Column | Values |
|---|---|
| `hgnc_symbol` | one HGNC symbol per row, as in `seeds.json`: matches `[A-Za-z0-9][A-Za-z0-9._@/-]*` after trimming, no `|` or control/line-break character, unique ignoring case |
| `tier` | `core` or `data` |
| `evidence` | why the gene is proposed |

`perturbations` (`target_layer` `maboss`):

| Column | Values |
|---|---|
| `scenario_id` | unique id |
| `context` | cell line or condition |
| `entity` | gene or compound name |
| `entity_type` | `gene` or `compound` |
| `targets` | HGNC symbols, `;`-separated |
| `effect` | `inhibit`, `activate`, `loss` or `gain` |
| `evidence` | source or statistic |

`validation_targets` (`target_layer` `maboss`):

| Column | Values |
|---|---|
| `target_id` | unique id |
| `statement` | the expected result in words |
| `test_context`, `reference_context` | the two contexts compared |
| `perturbation` | a `scenario_id` or an entity |
| `phenotype` | `proliferation`, `survival`, `migration`, `viability` or `other` |
| `expected` | `greater_drop`, `smaller_drop`, `decrease`, `increase` or `no_change` |
| `evidence_strength` | `strong`, `moderate`, `weak` or `exploratory` |
| `evidence` | source or statistic |

Report headings (final message, saved by the recorder as `report.md`). Write the headings
exactly `## Figures` and `## Abbreviations` (a leading section number such as `## 5. Figures`
is fine; no extra words after the title). `receive.py` requires both headings and every indexed
figure's file name inside the Figures section (a PNG/SVG pair counts once if the stem appears); with no figures, Figures says "none" but
Abbreviations is still required. The `Handoff:` line is last.

```markdown
# <title>
## Question and scope
## Sources
## Methods
## Results
## Figures
## Abbreviations
## Limitations
## Proposals and decisions
Handoff: runs/data-analyst/<id>/handoff.json sha256=<64hex>
```

- **Sources:** per source, the name, endpoint/URL, release/version, retrieval date, terms
  (as in the ledger) and which outputs and figures derive from it.
- **Methods** (scripts, parameters, seeds, vendored guides used) and **Results** cite figures
  inline, e.g. "differential expression (Fig. 4, `fig04_volcano_luad.png`)".
- **Figures:** one entry per figure: path, title, full description (what is shown, encodings,
  n, statistics, thresholds), the key observation, and its data source.
- **Abbreviations:** a glossary of every abbreviation used in figures and text (the union of
  the figures' `abbreviations` and any used in the prose).
- **Proposals and decisions:** what the researcher must approve (proposals and decision ids).

## 8. Citation reminder

Pass every vendored guide that informed the analysis to `manifest.py build --skills`
(for example `--skills pydeseq2 pathway-enrichment`) and list them in the report Methods,
so the analyses can cite K-Dense scientific-agent-skills (see `THIRD_PARTY_NOTICES.md`).

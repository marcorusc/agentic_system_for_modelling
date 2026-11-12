# Vendored scientific-agent-skills

- Upstream: https://github.com/K-Dense-AI/scientific-agent-skills
- Commit: `2d2065fb4520fa3f3f2bcf61cff26ec8b7eba4b5`
- Vendored on: 2026-11-12
- Upstream license: MIT (`LICENSE.md`); citation metadata in `CITATION.cff`.

These directories are data for the `data-analyst` specialist. They live outside
`.claude/skills/` and `skills/` on purpose so Claude Code does not discover or
auto-load them. Treat their scripts as untrusted until run by the guarded specialist.

## Skills

| Skill | License (SKILL.md frontmatter) | Author |
|---|---|---|
| `depmap` | CC-BY-4.0 | Kuan-lin Huang |
| `database-lookup` | MIT | K-Dense Inc. |
| `gget` | BSD-2-Clause | K-Dense Inc. |
| `bulk-rnaseq` | MIT | K-Dense Inc. |
| `pydeseq2` | MIT | K-Dense Inc. |
| `pathway-enrichment` | MIT | K-Dense Inc. |
| `cellprofiler` | MIT | K-Dense Inc. |
| `statistical-analysis` | MIT | K-Dense Inc. |
| `scikit-learn` | BSD-3-Clause | K-Dense Inc. |
| `uncertainty-and-units` | MIT | K-Dense Inc. |

Each skill keeps its own license; see `THIRD_PARTY_NOTICES.md` at the repository root.

## Local modifications

Upstream hashes for every file are recorded in `VENDOR.lock.json`; modified files
also record `local_sha256`, reason and date.

| File | Reason |
|---|---|
| `pydeseq2/scripts/run_deseq2_analysis.py` | In `save_results`, AnnData cannot serialize pandas `Series` stored in `uns` (e.g. `trend_coeffs`), so `write_h5ad` failed. They are converted to dicts before writing. Marked with a `# Local modification` comment (2026-11-12). |

## Re-sync procedure

1. Clone upstream into a new empty directory outside this repository and check out the new commit.
2. Copy the ten `skills/<name>/` directories, `LICENSE.md` and `CITATION.cff` over this tree (copy files only; do not execute upstream code).
3. Re-apply every modification listed above.
4. Update `UPSTREAM_COMMIT` in `scripts/data/vendor_lock.py`, this file, `THIRD_PARTY_NOTICES.md` and the README.
5. Rebuild the lock: `python3 scripts/data/vendor_lock.py build --upstream <clean checkout> --modified-reason PATH=REASON` (once per modified file).
6. Run `python3 scripts/data/vendor_lock.py verify` and `python3 -m unittest discover -s tests/data -v`.

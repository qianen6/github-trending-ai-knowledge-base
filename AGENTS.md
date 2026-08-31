# Repository agent instructions

Before every daily run, read `WORKFLOW.md`, `SCREENING_RULES.md`, `CARD_CONTENT_SPEC.md`, `DESIGN.md`, and `schemas/incoming.schema.json`.

## Mandatory card workflow

1. Collect all 21 official GitHub Trending pages and deduplicate by `full_name`.
2. Reuse stable repository evidence where permitted, but never copy an old `card` without rechecking it.
3. For every repository, separately read its README and selected official evidence, then synthesize the nine `card` fields according to `CARD_CONTENT_SPEC.md`.
4. Write the complete batch first to `proof/run-YYYY-MM-DD/incoming.candidate.json`.
5. Run:

   ```powershell
   python scripts/trending_engine.py validate-cards --root . --input proof/run-YYYY-MM-DD/incoming.candidate.json
   ```

6. If the result is not `CARD VALIDATE PASS`, rewrite every reported repository. Do not promote, ingest, render, or publish the draft.
7. After the card check passes, atomically promote the draft to `incoming/YYYY-MM-DD.json`, then run the fixed ingest/build/validate sequence in `WORKFLOW.md`.

## Mandatory Chinese README workflow

1. After ingest, compute the union of projects actually shown in all daily/weekly/monthly front-end boards; only this set needs localized README files.
2. Fetch each displayed project's official raw README. If it is Chinese-dominant, copy it directly; otherwise translate the complete README faithfully according to `README_TRANSLATION_SPEC.md`.
3. Update `readmes/manifest.json` with exact catalog coverage and source/translation hashes.
4. Run `python scripts/readme_translations.py validate --root .` before building the site.
5. If any displayed project translation is missing, stale, duplicated, mostly non-Chinese, too short for a faithful translation, or contains placeholders, do not build or publish.
6. Displayed project detail pages must embed the localized README under the `中文 README` heading; non-displayed catalog projects do not need one.

## Semantic separation

- `features` describes what users can do with the project.
- `strengths` describes advantages of the project itself.
- README, manifests, source entry points, tests, CI, Release, and documentation coverage belong to `quality.rationale` and evidence URLs.
- Trending periods and Stars belong to trend fields and may only supplement `why`.
- Static-review scope is a knowledge-base judgment boundary, not a project limitation.

Never generate card prose from category, programming language, directory presence, test presence, CI presence, score level, or Stars. Never reuse identical `features` or `strengths` arrays across repositories.

# Repository agent instructions

Before every daily run, read `WORKFLOW.md`, `SCREENING_RULES.md`, `CARD_CONTENT_SPEC.md`, `DESIGN.md`, and `schemas/incoming.schema.json`.

## Agent skills

### Issue tracker

Work is tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the canonical five-label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository. Read `CONTEXT.md` and `docs/adr/`; see `docs/agents/domain.md`.

## Mandatory Codex daily-task installation

When the user says `安装这个仓库并创建每日任务`, asks to install/initialize the downloaded repository, or asks for automatic daily operation, read and execute `CODEX_SETUP.md` in the same turn.

- Run the platform setup script and verify it.
- Search for and call the Codex app `automation_update` tool; do not stop after printing instructions or a prompt.
- Read `.codex/daily-task.json` as the portable installation contract and use the first `text` code block in `AUTOMATION_PROMPT.md` as the automation prompt.
- Resolve the downloaded repository's own absolute project ID and working directory; never reuse the publisher's local path.
- Inspect existing automations and update a matching task instead of creating a duplicate.
- Read the created/updated task back and verify its `ACTIVE` status, daily schedule, project ID, working directory, and prompt.

## Mandatory card workflow

1. Run `python scripts/collect_trending.py --root . --date YYYY-MM-DD --evidence` to collect the fixed 21-page matrix, hashed raw HTML, and cached official evidence. If a page fails, preserve its explicit failure record.
2. Read `proof/run-YYYY-MM-DD/collection.json` from the active workspace and deduplicate by `full_name`.
3. Reuse stable repository evidence where permitted, but never copy an old `card` without rechecking it.
4. For every repository, separately read its README and selected official evidence, then synthesize the nine `card` fields according to `CARD_CONTENT_SPEC.md`.
5. Resolve the active data root (`workspace/` when `workspace/.kb-workspace` exists, otherwise `.`), then write the complete batch to `<data-root>/proof/run-YYYY-MM-DD/incoming.candidate.json`.
6. Run:

   ```powershell
   python scripts/trending_engine.py validate-cards --root . --input <data-root>/proof/run-YYYY-MM-DD/incoming.candidate.json
   ```

7. If the result is not `CARD VALIDATE PASS`, rewrite every reported repository. Do not promote, ingest, render, or publish the draft.
8. After the card check passes, atomically promote the draft to `incoming/YYYY-MM-DD.json`, then run the fixed ingest/build/validate sequence in `WORKFLOW.md`. Ingest must produce a valid DailyEdition and publication transaction manifest.

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

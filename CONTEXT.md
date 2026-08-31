# Domain context

## Purpose

This repository turns the fixed official GitHub Trending matrix into a reproducible Chinese knowledge base. It preserves raw evidence, evaluates every deduplicated candidate, publishes selected projects, localizes displayed READMEs, and builds a static offline site.

## Domain glossary

- **Trending page** — one official GitHub Trending page for a specific period and language scope.
- **Appearance** — one repository occurrence on one Trending page, including rank and period Stars.
- **Candidate pool** — all repositories deduplicated by `full_name` across the 21 Trending pages.
- **Evidence record** — a hashed raw page or official repository response used for static verification.
- **Incoming batch** — the complete 21-page batch plus one enriched repository object for every candidate.
- **Evaluation** — the H/T/Q/V/F result for one candidate on one capture date.
- **Catalog entry** — the durable accepted-project record, deduplicated across dates.
- **DailyEdition** — the structured, canonical daily publication record containing statistics and the daily/weekly/monthly featured project lists.
- **Displayed project** — a project referenced by a DailyEdition and therefore requiring a localized README.
- **Localized README** — a source-hash-bound Chinese copy or faithful translation of the displayed project's official README.
- **Publication transaction** — the staged set of run artifacts promoted together after validation.
- **Project root** — source code, rules, schemas, tests, and installation contracts.
- **Workspace** — mutable captures, evidence, evaluations, catalog, reports, localized READMEs, and generated site.

## Invariants

1. The candidate pool contains only the official 21-page Trending matrix.
2. `raw_candidate_count == evaluated_candidate_count` after `full_name` deduplication.
3. Candidate repositories are never cloned, installed, imported, or executed.
4. Card features describe user-visible capabilities; strengths describe project advantages.
5. DailyEdition is the source of truth for front-end selection and README coverage.
6. A publication is complete only after its transaction manifest is committed.
7. Legacy root workspaces remain readable; new installations use `workspace/`.

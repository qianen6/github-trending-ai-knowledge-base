# ADR-0002: Publish through DailyEdition and a transaction manifest

- Status: Accepted
- Date: 2026-08-31

## Decision

Generate one structured `daily/YYYY-MM-DD.json` DailyEdition during ingest. Markdown daily reports, HTML boards, and localized README coverage consume this record. Stage every ingest artifact below `.kb-state/staging/`, promote the complete set through `ArtifactTransaction`, and write the commit manifest last.

## Consequences

- Display selection no longer depends on parsing Markdown headings.
- A failed promotion restores prior files and leaves no successful commit manifest.
- Historical Markdown-only runs remain supported through a legacy adapter.

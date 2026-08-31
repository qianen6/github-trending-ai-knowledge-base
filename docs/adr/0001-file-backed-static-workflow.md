# ADR-0001: Keep a file-backed static workflow

- Status: Accepted
- Date: 2026-08-31

## Decision

Keep JSON, Markdown, raw evidence files, and generated HTML as the durable storage format. Do not add a database or execute candidate repositories. Centralize every mutable path through `WorkspaceLayout` and use `workspace/` as the only data root.

## Consequences

- Outputs remain inspectable, portable, diffable, and usable through `file://`.
- Publication needs explicit transaction and manifest logic because multiple files form one run.
- Any future storage adapter must preserve the same domain invariants and offline export.

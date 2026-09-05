# ADR-0003: Validate staged releases and bind cached content

- Status: Accepted
- Date: 2026-09-05

## Decision

Keep ADR-0001's file-backed workflow and ADR-0002's DailyEdition. Add a Daily run Module whose prepare step ingests into an isolated workspace and whose publish step validates localized READMEs, the staged site and the data before promoting one artifact transaction. Record stage input/output fingerprints and timings for verifiable resumption.

Recovery treats a matching, hash-valid commit marker as authoritative and finishes cleanup rather than rolling back a committed generation. OS-owned writer locks prevent a live writer from being mistaken for an interrupted one. Optimistic fingerprints reject publication over changed live data.

Bind Localized README entries to immutable raw snapshots under readmes/sources. Compare source-copy text and CommonMark code/heading structure. Cache rendered fragments by text, implementation and dependency fingerprints, with output-hash verification.

Expose every Catalog entry through a static HTML directory; this does not change DailyEdition selection or localized README coverage. Archive only old rollback-test copies after reference checks, streamed archive verification and source rechecks; keep raw evidence and provide restoration.

## Consequences

- Existing individual CLI adapters remain usable; the staged publish path is preferred for daily releases.
- Failure leaves formal data/site unchanged when using staged publication; failed stages remain inspectable.
- Rendering and passed checks can be reused only when their dependencies and outputs remain identical.
- Structural translation checks are not proof of semantic fidelity.
- No database, external CDN or front-end framework is introduced.


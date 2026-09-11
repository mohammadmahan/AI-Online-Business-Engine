# docs/

Documentation index for the AI-First Online Business Engine.

Root-level documents (`README.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`,
`SECURITY.md`, `DECISIONS.md`, `TODO.md`, `MASTER_PLAN.md`,
`PROJECT_RULES.md`) are the primary references. This directory holds
supporting material: shared vocabulary and per-phase working documents.

## Contents

| Path | Purpose |
| --- | --- |
| [glossary.md](glossary.md) | Shared vocabulary: entities, provenance states, autonomy tiers, conventions. |
| [phases/](phases/) | Per-phase scope, entry/exit criteria, and Definition-of-Done tracking. |
| [phases/phase-01-project-architecture.md](phases/phase-01-project-architecture.md) | Phase 1 — Project Architecture. |

## Conventions

- Documentation is written in English. Product/customer-facing language is
  Persian / RTL-first; that requirement applies to future storefront work,
  not to project documentation.
- Documents must not contain secrets, credentials, or customer data
  (see `SECURITY.md`).
- Documentation must be updated when architecture, data ownership, API
  behavior, security, deployment, workflow behavior, or important business
  rules change (`PROJECT_RULES.md` §37). Documentation must never become
  silently false.
- Directories are created only when they have real content; no empty
  placeholder directories.

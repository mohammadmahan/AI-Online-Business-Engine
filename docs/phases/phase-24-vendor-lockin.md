# Phase 24 — Vendor Lock-in & Neutral Portability Layer (D-129–D-132)

- Status: **specification (M0) — decisions PROPOSED, pending owner
  approval; implementation gated on approval**
- Discipline: local-first (D-053), design-first, zero-skip testing;
  strictly localhost/air-gapped (D-045); deterministic execution;
  canonical core stays pure (RULES §35 boundary discipline).

## 0. Governance reconciliation (read this first)

- MASTER_PLAN §13 defines Phase 24 as **"Vendor Lock-in"**: *keep
  provider integrations replaceable where practical, using clear
  provider boundaries.* This spec formalizes the boundaries that the
  platform has practiced since Phase 7 into declared, battery-proven
  contracts — and adds the swap/fallback/parity battery that makes
  replaceability a TESTED property instead of an assertion.
- **Existing neutral surfaces to formalize (inventory, not new
  build):**
  - AI: `AiProvider` (canonical, Phase 7) with `MockAiProvider`
    (deterministic local), `OpenAiProvider` / `AnthropicProvider`
    (owner-gated live adapters, Phase 8), `FallbackProvider`
    (graceful isolation, D-066).
  - Blob/media: `MediaStore` ABC + `LocalObjectStore` +
    `media_store()` factory (S3-compatible operation semantics,
    local emulator D-056).
  - SQL/memory backends: `EventStore` (JSON parity) vs
    `PgEventStore` (D-027), `_JsonSlotLocks` vs `_PgSlotLocks`
    (D-095/D-096), notification delivery parity backends.
  - Publishing channels: `InstagramAdapter` / `MockInstagramAdapter`
    / `GraphApiAdapter`, `TelegramAdapter`, fan-out bridge
    (provider-neutral, Phase 11).
- **What is genuinely NEW in Phase 24:** the canonical CONTRACT
  REGISTRY that binds all of the above into one portability
  taxonomy; the PARITY HARNESS that proves backend pairs behave
  identically; the SWAP/LOCKOUT protocol (deterministic fallback and
  hot-swap semantics); and the D-132 battery. Plus one real gap:
  provider-agnostic token accounting write-through into the D-127
  budget ledger for ALL providers (live adapters currently meter via
  the D-063 collector — the write-through is formalized here).
- **Registration discipline:** D-129–D-132 are recorded as
  **Proposed** (register row 40) per the D-064 reconciliation rule;
  implementation (M1–M4) starts only after owner approval.

## 1. Decision table (PROPOSED)

### D-129 — Model & provider neutrality contract (AiProvider v2)

- **Situation:** the `AiProvider` boundary works but is enforced by
  convention; there is no battery proving that EVERY provider
  implementation (mock, OpenAI, Anthropic, local/self-hosted, and
  any future one) is schema-compatible, meters tokens identically,
  and leaks zero provider-specific payload structure into canonical
  records.
- **Decision (PROPOSED):**
  1. **Provider contract v2** (`canonical/portability.py`):
     `ProviderContract` — a declared checklist every `AiProvider`
     must satisfy: deterministic `name`; `generate(AiRequest) →
     AiResponse` with schema-compatible output for every declared
     schema id; token accounting fields always present
     (prompt/completion tokens, latency, estimated cost) and
     WRITE-THROUGH to the D-127 `BudgetLedger` via the existing
     collector path; failure surfaces as exceptions carrying the
     D-052 `failure_class` (A/B/C/E) — never bare provider SDK types.
  2. **Conformance harness:** `assert_provider_conformance(provider,
     schemas)` — one call battery-proving any implementation against
     the checklist (mock live-tested; OpenAI/Anthropic conformance
     is exercised with owner-gated offline fixtures until credentials
     exist — conformance does NOT prove live compatibility).
  3. **Zero-leak clause (D-124 extension):** provider payloads,
     model names, and SDK metadata may appear ONLY in observability
     records (`ai.observe.v1`), never in canonical business state.
- **Consequences:** adding a provider = implementing one interface +
  passing one harness call; lock-in becomes structurally visible
  (a provider that cannot conform IS the lock-in, surfaced as a
  battery failure).

### D-130 — Storage & database abstraction boundaries

- **Situation:** domain logic already runs over injected backends,
  but the parity guarantee (JSON vs PG behave identically) is proven
  ad hoc per phase; blob operations have an ABC but no declared
  conformance contract; ANSI-SQL portability is implied, never
  stated.
- **Decision (PROPOSED):**
  1. **Backend parity contract** (`canonical/portability.py`):
     `BackendPair` — a declared (name, offline_factory,
     live_factory) pair plus the operation matrix every backend
     family must satisfy (D-027 event store ops, slot-lock ops,
     notification locks, media ops). `assert_backend_parity(pair)`
     runs the SAME operation script against both factories and
     compares normalized verdicts — any divergence is a battery
     failure. This solidifies the existing EventStore/PgEventStore,
     Json/PG slot locks, and notification parity into one declared,
     reusable harness.
  2. **Blob/media conformance:** `MediaStoreContract` —
     put/get/delete/list/stat semantics, deterministic content
     addressing, zero wall-clock in metadata; `LocalObjectStore`
     conforms now (battery-proven), S3-compatible remotes are
     drop-in conformers (owner-gated).
  3. **SQL portability statement:** canonical SQL stays in the
     psql-transport + schema layer (declared files only); domain
     modules never embed vendor idioms (no `ON CONFLICT` outside
     transport, no procedural SQL) — AST-enforced. Hermetic memory
     backends remain the canonical offline tier.
- **Consequences:** swapping PostgreSQL for another ANSI-SQL engine
  (or a memory backend for hermetic runs) is a parity-harness pass,
  not an archaeology project; blob vendors are ABC conformance.

### D-131 — Pluggable integration adapters (channels & tooling)

- **Situation:** Instagram/Telegram adapters and notification
  channels are injectable, but there is no declared interchange
  protocol — what a "swap" means operationally (registry, health,
  fallback), and no battery proving canonical workflows are
  untouched by adapter identity.
- **Decision (PROPOSED):**
  1. **Adapter interchange protocol**
     (`canonical/portability.py`): `ChannelAdapterContract` —
     declared lifecycle per channel adapter: deterministic
     `name`; mock/live variant pair; route/dispatch envelope
     parity (mock and live return the SAME envelope shape);
     failure classes via D-052; hot-swap = registry rebind with a
     deterministic verdict (`swapped_from`/`swapped_to`/`swapped_at_logical`)
     audited through the D-121 log ledger.
  2. **Workflow isolation clause (battery-asserted):** canonical
     workflow modules (fan-out, orchestration, notification) must
     contain ZERO channel-name conditionals (`instagram`/`telegram`
     literals outside the adapter modules themselves) — routing is
     data (targets lists), never code branches. Extended AST rule
     added to the D-116 sweep.
  3. **External operational tooling** (n8n, admin CLI, dashboard):
     consume ONLY canonical contracts/facades — never adapter
     internals; already the practice, now a declared rule the sweep
     audits.
- **Consequences:** a new channel (e.g., a staging gateway) is one
  adapter class + one registry entry + one conformance pass;
  canonical workflows cannot grow vendor tentacles.

### D-132 — Portability & port-swapping verification battery

- **Situation:** the neutrality claims above need the same
  zero-skip closure as every prior phase.
- **Decision (PROPOSED):** `local/tests/test_phase24_portability.py`
  with offline + live-PG classes covering: provider conformance
  (mock + fixture-driven), token-accounting write-through into the
  D-127 ledger, backend parity across the declared pairs (offline
  always; live-PG when the stack is up), media conformance,
  hot-swap protocol verdicts, simulated provider lockout
  (primary dead ⇒ deterministic fallback ⇒ observability records
  the isolation, D-066), workflow-isolation AST rules, and
  zero-secret boundary checks. Full battery ×2 green, census
  reconciles, sweeps CLEAN.

## 2. Architecture

```
canonical/portability.py (pure contracts + harnesses, no I/O)
  ProviderContract ──> assert_provider_conformance ──> battery verdict
  BackendPair      ──> assert_backend_parity (same script, 2 factories)
  ChannelAdapterContract ──> swap registry (deterministic verdicts)

existing seams bound IN:
  AiProvider family ──> D-127 BudgetLedger write-through (D-063 path)
  MediaStore ABC ──> LocalObjectStore now, S3-compatible remotes later
  EventStore/locks/notification parity backends ──> one harness
  Instagram/Telegram/mock adapters ──> registry rebind + D-121 audit
```

## 3. Milestones (implementation gated on D-129..D-132 approval)

- **M1 (Contracts):** `local/canonical/portability.py` —
  ProviderContract checklist, BackendPair declaration + operation
  matrix, ChannelAdapterContract, conformance/parity harness
  primitives (pure, offline).
- **M2 (Bindings):** declare the concrete pairs/registry — AI
  provider set + budget write-through, event/lock/notification
  backend pairs, media conformance for `LocalObjectStore`, channel
  adapter registry with hot-swap semantics + D-121 audit rows.
- **M3 (Sweep extension):** workflow-isolation AST rule
  (channel-name literals confined to adapter modules) added to the
  D-116 extended sweep + Phase 20 pin updates.
- **M4 (Battery & closure):** `test_phase24_portability.py`,
  battery ×2 green, census, sweeps, docs (verification record,
  MASTER_PLAN, TODO, DECISIONS notes), commit + push.

## 4. Verification gates (same as every phase)

- Zero-skip battery; two consecutive green runs; census reconciles
  exactly; extended AST sweep + secret-entropy scan + bounds
  re-audit CLEAN; `git diff --check` PASS; stack 5/5 healthy;
  live-layer tests run (not skipped) while Colima/Docker is up.

## 5. Open items for the owner

1. **Approve / amend D-129..D-132** (registered as Proposed).
2. Confirm the declared backend pairs to guarantee under parity
   (proposal: event store, slot locks, notification locks, media —
   all four; adding more later is additive).
3. Confirm hot-swap auditing destination: D-121 `engine.log.v1`
   ledger (proposed) vs Phase 19 control-audit chain (owner call —
   both are defensible; the ledger keeps the audit chain
   append-only-pure for human decisions).

"""local/src/publishing — multi-channel publishing orchestrator
adapters (D-142 feedback loop + fault-tolerance hardening).

Composes the canonical Phase 10/11 engines (scheduling calendar,
fan-out orchestration, outbox publishers) with the D-142 memory
layer. The canonical engines stay untouched; these adapters add the
cross-cutting concerns the directive names:

  - `retry_policy`   deterministic exponential backoff + DLQ
                     classification (no jitter — D-126).
  - `telegram` / `instagram`  receipt-normalizing dispatchers over the
                     canonical outbox publishers.
  - `orchestrator`   schedule-triggered dispatch with per-target retry
                     decisions, durable dead-letter routing, and
                     budget-gated engagement feedback into memory.
"""

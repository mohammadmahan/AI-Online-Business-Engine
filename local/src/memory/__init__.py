"""D-142 — portable multi-agent shared memory layer.

Two surfaces:
  - `vector_store`   pgvector-compatible SSOT-backed memory store
                     (schema DDL, injected-executor adapter, HNSW
                     hooks, deterministic summarization pruning).
  - `memwal_adapter` portable WAL export/sync adapter following the
                     MystenLabs/MemWal portable-memory pattern, with a
                     transparent local-SSOT fallback (D-045: remote
                     Walrus/relayer connectivity is NEVER attempted
                     without an owner-authorized injected transport).

Memory is NEVER authority (D-026/D-027): business truth and approvals
stay in the canonical store and the Phase 19 control chain.
"""

"""D-142 — portable multi-agent shared memory layer.

Three surfaces:
  - `vector_store`    pgvector-compatible SSOT-backed memory store
                      (schema DDL, injected-executor adapter, HNSW
                      hooks, deterministic summarization pruning).
  - `memwal_adapter`  portable WAL export/sync adapter following the
                      MystenLabs/MemWal portable-memory pattern, with a
                      transparent local-SSOT fallback (D-045: remote
                      Walrus/relayer connectivity is NEVER attempted
                      without an owner-authorized injected transport).
  - `memwal_transport` the envelope contract that injected transport
                      must satisfy (`memwal.transport.v1`): deterministic
                      idempotency keys, bounded chunking, D-044 error
                      taxonomy, edge redaction, never raises to the agent.

Memory is NEVER authority (D-026/D-027): business truth and approvals
stay in the canonical store and the Phase 19 control chain.
"""

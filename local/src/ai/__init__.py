"""local/src/ai — AI-pipeline adapters that compose canonical contracts.

Distinct from `local.canonical.ai_runtime` (pure domain core): these
modules are runtime-adjacent bindings (memory context, cross-cutting
interceptors) that obey the repository discipline — injected
dependencies only, fail-closed defaults, deterministic behavior, no
network (D-045).
"""

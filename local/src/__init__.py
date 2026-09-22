"""local.src — portable subsystems that compose canonical contracts.

Distinct from `local.canonical` (pure domain core): these modules are
infrastructure-adjacent adapters (storage engines, external client
seams) that still obey the repository's discipline — injected
transports only, no wall clock, no credentials, fail-closed defaults.
"""

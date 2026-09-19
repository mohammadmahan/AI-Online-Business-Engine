# SECURITY

Security baseline and safety rules for the AI-First Online Business
Engine.

**Status:** Security rules from `MASTER_PLAN.md` §5, §9–§11 and
`PROJECT_RULES.md` §3–§4, §16–§22, §27–§33. This document defines rules
only. No hosting, no tooling, no credentials, and no provider-specific
configuration exist yet; those arrive with their phases and will be
added here without changing the rules.

**This file must never contain secrets, API keys, endpoints, account
names, or customer data.**

---

## 1. Security baseline

Required for every production-facing component:

- HTTPS / SSL
- Secret management
- API-key protection
- Webhook authentication
- Least privilege
- 2FA where available
- Backups
- Audit logging
- Error monitoring
- Development / production separation
- Credential rotation
- Recovery procedures

(MASTER_PLAN §10)

Concrete implementations (backup tooling, monitoring stack, WAF, etc.)
are chosen per phase and recorded in `DECISIONS.md`. Until then this
baseline is the acceptance criterion for every phase that touches
production.

## 2. Secrets and credentials

Secrets are never placed in (RULES §16):

- Source code
- Git (any commit, any history)
- Markdown / documentation / README
- Screenshots
- Logs
- Public repositories
- Hard-coded workflow nodes

Storage: secure credential storage or environment variables. No product
is selected yet (Open decision, Phase 5).

Rules:

- Grant only necessary permissions; no broad production access for
  convenience (RULES §17).
- Freebuff and AI agents must not receive unrestricted production
  credentials by default.
- Rotate credentials on schedule and after any exposure; rotation
  procedures are defined when infrastructure exists (Phase 4).
- **If a secret is exposed: STOP and report it immediately; rotate when
  appropriate.** (RULES §16)

## 3. Human authority

The human owner has final authority over (RULES §3): business
decisions, major architecture, production infrastructure, payment,
financial operations, refunds, credentials, security, deployment, data
deletion, vendor selection, major vendor dependencies.

Major architecture changes require **STOP → EXPLAIN → APPROVAL** before
implementation (RULES §4): database architecture, ecommerce source of
truth, authentication, payment, security, infrastructure, API strategy,
data ownership, major vendor dependency, production deployment.

## 4. Destructive operations

Require explicit human approval (RULES §22):

- Delete database data
- Delete customer records
- Delete products
- Delete files
- Drop tables
- Reset production
- Revoke credentials
- Rewrite Git history
- Replace production configuration

Undoing code does not automatically undo external side effects (RULES
§26). Before high-risk changes, identify backup, rollback method,
recovery owner, and failure modes.

## 5. AI safety rules

### 5.1 Never invent data

AI must never invent (RULES §6, MASTER_PLAN §5): product specifications,
material, color, size, measurements, price, discount, stock, shipping
time, payment status, order status, customer information.

Unavailable information is `UNKNOWN` or `NOT_PROVIDED`, or the request
is escalated for clarification.

### 5.2 Provenance

AI-generated information must remain distinguishable from verified
information at all times:

- `AI_GENERATED` / `HUMAN_REVIEWED` / `HUMAN_VERIFIED`

AI inference must never be presented as verified fact.

### 5.3 Autonomy tiers

(MASTER_PLAN §9, RULES §32 — see `docs/glossary.md`)

- **Green — autonomous:** classification, formatting, drafts, internal
  summaries, low-risk transformations.
- **Yellow — monitored:** customer reply drafts, product descriptions,
  lead classification, marketing drafts, recommendations.
- **Red — human approval:** refunds, financial actions, production
  price changes, credential changes, security changes, destructive
  operations, permanent deletion, high-impact disputes, high-risk
  production deployment.

### 5.4 AI output validation

Before AI output affects business systems it must pass schema
validation and deterministic checks (RULES §33). Never directly trust
model output for: price, inventory, payment, refunds, customer
identity, order status, destructive operations.

## 6. Instagram

- Prefer official Meta/Instagram APIs and supported integrations
  (RULES §29).
- Avoid fragile unofficial automation for critical production workflows
  when a supported API exists.
- Customer-facing AI must use verified product and order data.
- Escalate when the model is uncertain, information is unavailable, the
  issue is financially sensitive, or the action is irreversible or
  high-risk.

## 7. Payment

- Payment status must be verified server-side — never from client
  callbacks alone (RULES §30).
- Before production: provider selected, callback behavior tested,
  verification implemented, duplicate callbacks handled, failed
  payments handled, logging implemented, human approval obtained.
- No automatic refunds without an approved safe workflow.

Provider selection is an Open decision (Phase 12).

## 8. Shipping

- Shipping data comes from verified business/provider data only (RULES
  §31).
- Never invent: shipping price, delivery date, tracking number,
  shipment status.

Provider selection is an Open decision (Phase 13).

## 9. Customer data minimization

- Collect only necessary customer information.
- Do not duplicate personal information without reason.
- Minimize operational copies in Notion.
- Expose customer data to AI only when necessary.
- Never log secrets; minimize sensitive customer data in logs (RULES
  §27).

## 10. Environments

```text
Development -> Testing/Staging -> Production
```

- No experimental code against production payment, inventory, or
  customer systems (RULES §18).
- High-risk changes follow Development → Test → Review → Approval →
  Production (RULES §43).
- **Deployment tooling (D-141, Proposed — PLANNED):** if Dokploy is
  adopted (`docs/deployment/dokploy-plan.md`), its administrative
  surface follows the same secrets posture as everything else
  (D-045): UI never public, key-only SSH, scoped least-privilege
  credentials for GitHub/webhooks/S3 backups, per-environment
  credential isolation, and rotation entries in the DR runbook.
  Deployment-tool credentials never carry production authority —
  production activation stays behind D-139 one-time owner tokens,
  and a GitHub push or webhook event never authorizes a Production
  deployment.

## 11. Error handling, logging, observability

- Never hide errors; never swallow errors to make a workflow appear
  successful (RULES §24).
- Never claim success when something partially failed (RULES §41).
- Important systems must be able to answer: what happened, when, which
  workflow, which event, which system, success/failure, retry status,
  human involvement (RULES §27).
- Never log secrets.

## 12. Git hygiene

- Never commit passwords, tokens, API keys, private credentials, or
  unnecessary sensitive customer data (MASTER_PLAN §11, RULES §19).
- Destructive Git operations (history rewrites, force pushes) require
  explicit approval.

## 13. Testing for safety

Financial, payment, inventory, and order workflows require failure
testing before production (RULES §23): normal, empty, missing, invalid,
duplicate, API failure, timeout, authentication failure, rate limit,
partial failure, malformed AI output, rejection, retry, and recovery
cases.

## 14. Incident handling (baseline)

Until dedicated tooling exists (Phase 22), the procedure is:

1. Stop the affected workflow/agent.
2. Report the incident immediately and honestly — including partial
   failures.
3. Rotate exposed credentials when appropriate.
4. Identify backup/rollback options before changing anything further.
5. Record the incident and resolution in `DECISIONS.md` or the phase
   log.

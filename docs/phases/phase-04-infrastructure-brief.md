# Phase 4 — Infrastructure: Decision Brief (DESIGN ONLY)

Status: **Brief prepared (2026-09-13, owner-sequenced)** — no
infrastructure created, no credentials requested, nothing deployed.
Every option below is an **owner decision gate** (RULES §4/§22).

Owner sequencing (2026-09-13): the **Data Entry & Verification Engine**
runs locally first (implemented on the Batch 4 scaffolding), and this
brief runs in parallel; **official MASTER_PLAN Phase 4 (Infrastructure)
gates remain open** until the owner chooses.

---

## 1. Scope reminder (MASTER_PLAN §13, verbatim intent)

Phase 4 = VPS/hosting, backups, monitoring, DNS, SSL, environment
separation, deployment and recovery. Local development (D-053/D-054)
is deliberately separate — **the local stack is not staging**, and no
Phase 4 item is closed by local-only work.

## 2. Decision gates and options

### G1 — Hosting / VPS (register row 6)
| Option | Pros | Cons |
|---|---|---|
| Iranian managed WP host | sanctions/payment simplicity, local CDN peers, Persian support | less n8n/PostgreSQL control; per-app isolation |
| Iranian VPS (e.g., dedicated) | full Docker control (compose = same stack as local), cost | self-managed backups/SSL/updates |
| Foreign VPS + CDN | ecosystem | sanctions/payment risk, latency for local buyers |

**Recommendation:** Iranian VPS running the same Docker Compose model
as D-054 (one manifest, three environments) + Iranian CDN for media.
Consequence: staging/prod reuse local skills 1:1.

### G2 — WordPress/WooCommerce instance model
Single WP multisite vs **separate staging + production instances**
(same image, separate DB/volumes, env-only differences). Recommended:
separate instances (clean env separation, RULES §18; staging = the
promotion gate before production).

### G3 — Media provider (D-049 provider gate; register row 6-adjacent)
Object storage compatible with the D-056 abstraction: Iranian S3-like
services (ArvanCloud/Liara-style) vs self-hosted MinIO on the VPS vs
foreign providers (sanctions/payment risk). Recommended: Iranian
object storage; the D-049/D-056 adapter keeps it swappable (env-only).
Media **binaries live there, never in Git**; Woo holds references.

### G4 — Backups & recovery
Minimum: nightly automated DB dump (Woo DB + canonical DB) + media
bucket sync + weekly full snapshot; documented restore drill. Owner
confirms retention and off-site location. Recommended: managed VPS
snapshots + object-storage versioning.

### G5 — Domain / DNS / SSL
Domain already planned (store + api hostnames); DNS at the registrar
or the CDN provider; **Let's Encrypt automated certificates**
(certbot/managed host). No secrets in Git (D-045) — DNS/SSL config is
environment configuration, not code.

### G6 — Monitoring / observability
Start minimal per phase-03-3 §17: structured JSON logs + uptime check
+ Woo/canonical health endpoints (the compose healthchecks already
define these). Upgrade path: uptime service + log shipping later
(Phase 22 "Observability" per MASTER_PLAN).

### G7 — Environment separation & promotion
Formalize the D-053 contract: **LOCAL → STAGING → PRODUCTION** with
"change configuration, not business logic". Promotion gate: the D-052
test ladder green on staging, owner approval for production (Red tier
per RULES §32).

## 3. What this brief deliberately does NOT do
No server provisioned, no domain registered, no credentials, no DNS
changes, no backups configured, no production data. All G1–G7 stay
**Open** until the owner approves each; the register keeps them open
(register row 6 and D-049's provider gate).

## 4. Suggested decision order
1. G1 + G2 (hosting model) → 2. G5 (domain/SSL) → 3. G3 (media
provider) → 4. G4 (backups) → 5. G6/G7 (monitoring/promotion).
Each approval gets a D-number and closes its register gate.

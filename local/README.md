# Local Development Environment (Phase 3 Batch 4 scaffolding)

LOCAL-ONLY implementation of the approved D-053/D-054/D-055/D-056
design (`docs/phases/phase-03-3-local-development-environment.md`).
Design record and component architecture live there; this guide is the
operational runbook.

## Structure

```text
local/
├── infra/
│   └── docker-compose.yml      # D-054 stack: wordpress+woo, mysql,
│                               # postgres (canonical), n8n, minio, mock
├── db/
│   └── schema.sql              # D-055 canonical schema (5 schemas)
├── canonical/                  # pure business-rule layer (no I/O)
│   ├── vocab.py                #   Registry v1 seed (D-031/D-032)
│   ├── identifiers.py          #   D-014/015/017/026/027/046 rules
│   ├── prices.py               #   D-024/025 resolution + D-048 projection
│   ├── excel.py                #   D-033/D-028 workbook validation
│   └── tests.py                #   unit tests (stdlib unittest)
├── services/
│   ├── mock_woo.py             # D-052 layer-2 mock adapter (D-043 iface)
│   └── media_store.py          # D-049/D-056 abstraction + local backend
├── scripts/
│   ├── local_env.py            # up / stop / down / status / reset-volumes
│   ├── apply_schema.py         # idempotent schema application
│   ├── seed_registry.py        # owner-approved vocabulary seed + verify
│   ├── smoke_test.py           # §17 10-point smoke test (+DB checks)
│   └── make_fixtures.py        # D-033 fixture workbook generator
└── fixtures/                   # product-master fixture + summary
```

## Requirements

- Docker Desktop for Mac (not yet installed on this machine — the
  compose stack needs it) — `brew install --cask docker` installs it.
- Python 3.9+ (system Python works; no packages required for the core
  tests — `openpyxl` only renders the `.xlsx` fixture).

## Start / stop / reset (all strictly LOCAL)

```bash
# bring the stack up, wait for health checks, apply schema, seed vocabulary
python3 local/scripts/local_env.py up

# apply/verify schema + seed without starting containers (needs only a
# reachable postgres)
python3 local/scripts/apply_schema.py
python3 local/scripts/seed_registry.py

# stop (keeps volumes) / remove containers (keeps volumes) / inspect
python3 local/scripts/local_env.py stop
python3 local/scripts/local_env.py down
python3 local/scripts/local_env.py status

# DESTRUCTIVE, LOCAL-ONLY: drops local volumes + all local test data,
# then recreates and reseeds. Requires typing RESET-LOCAL.
python3 local/scripts/local_env.py reset-volumes
```

`reset-volumes` deletes exactly: docker volumes `engine-local_woo_data`,
`engine-local_woo_data_db`, `engine-local_canonical_data`,
`engine-local_n8n_data`, `engine-local_media_data`, `engine-local_mock_state`,
plus `local/volumes/mock-woo/state.json`. It cannot reach staging or
production — those environments do not exist locally and no staging/
production target is referenced anywhere in this tooling.

## Tests

```bash
python3 -m unittest local.canonical.tests -v   # rule-layer units
python3 local/scripts/make_fixtures.py         # fixture matrix profile
python3 local/scripts/smoke_test.py            # §17 10-point smoke (+DB)
```

## Configuration & secrets

- Only `.env.example` is committed (dummy local defaults).
- `.env.local` / `.env.staging` / `.env.production` are gitignored;
  real values never enter Git, Markdown, Excel, AI prompts, or logs
  (D-045 / PROJECT_RULES §16).
- Compose service credentials shown in `docker-compose.yml` are
  **throwaway local-only values** by design (the file is the local
  runtime config, not a secret store); they are never valid anywhere
  else.

## Security posture

- All published ports bind `127.0.0.1` only.
- No production endpoints, credentials, webhooks, customer data, or
  payment data exist or are referenced.
- The mock adapter is explicitly NOT WooCommerce.
- Inventory remains read-only (D-041/D-016.I open).

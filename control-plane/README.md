# control-plane/

Read-only operations and business console for the AI-First Online Business
Engine. It is a Next.js presentation surface for local operator use; it does not
own or write the canonical database (D-171 §2.1).

## Data provenance

- `dashboard`, `orders`, `inventory`, and `hitl-queue` currently instantiate
  **deterministic MOCK** sources. Their screens say `دادهٔ نمونه` / `MOCK`; those
  readings are not live health or business evidence.
- `automations` is the only route that resolves `CP_TELEMETRY_MODE`. With
  `LIVE`, it uses the read-only probe seam; with `MOCK` (the default), it uses
  deterministic mock telemetry. `LIVE` does **not** make the other pages live.
- A missing or failed probe is rendered as `UNKNOWN`, never as healthy or zero.
- The console holds no credentials and has no write path. Emergency controls are
  rendered disabled with their reason.

## Local start and verification

```bash
cd control-plane
npm ci
npm run dev                    # binds 127.0.0.1 by default
# or, after npm run build:
npm start                      # binds 127.0.0.1 by default

npm run typecheck
npm run lint
npm test
npm run check:contrast
npm run check:live-verdicts
npm run build
```

`CP_TELEMETRY_MODE` and `CP_PROBE_ENDPOINTS` are read from the local environment
or `.env.local`. Probe endpoints must be loopback addresses. See
`docs/deployment/control-plane-container-spec.md` for the container contract.

## Exposure limit

**Loopback only.** The local `dev` and `start` scripts bind `127.0.0.1`
explicitly. The app has no authentication boundary, so it must not be published
on `0.0.0.0`, a LAN interface, a public tunnel, or a remote host. Non-local
access requires an owner-approved authentication and authorization design; it is
not authorized by this README.

The production container contract may bind `0.0.0.0` inside an isolated
container network only when an authenticated ingress and owner authorization
exist. That activation remains owner-gated (D-139).

## View isolation

The business and technical views share one dashboard. Technical-only diagnostics
are intentionally hidden from the business view. Run `npm run
check:view-isolation` against a running server to verify the rendered boundary.

## Limitations

- Most pages are mock-only; absence of live data is not a service outage.
- No accounts, sessions, roles, or per-action audit.
- No write actions are exposed.
- No live-provider credentials or external side effects are part of this console.

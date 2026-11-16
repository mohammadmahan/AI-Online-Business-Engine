# Local commerce demo — start, sign in, and safe restart

Development-only runbook for the existing local commerce demo. It uses the
`commerce-dev` stack, the intended `commerce-dev-postgres` database, mock
payment and mock SMS. It never contacts WooCommerce, ZarinPal, Kavenegar or any
other external service, and it does not use the Gate A harness.

Run the commands below from the repository root (`AI-Online-Business-Engine`) in Git Bash.

## 1. Set or rotate the local admin password

The admin password is entered interactively and never passed as a command-line
argument, echoed, or written to the repository. Only its scrypt hash and a
session secret go into the gitignored `.env`.

```bash
cd AI-Online-Business-Engine/commerce
bash scripts/setup-demo-admin.sh
```

- Accept the default username `owner` or enter your own (1–64 safe characters).
- Enter a password of at least 12 characters, then repeat it.
- The script writes `commerce/.env` with owner-only permissions where supported.
- It prints no credential value.

Rotating the password or session secret signs out existing browser sessions.

## 2. Start the demo stack

```bash
cd AI-Online-Business-Engine/commerce
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --wait postgres commerce-web
```

Expected state: `commerce-dev-postgres` healthy on `127.0.0.1:55433` and
`commerce-dev-web` healthy on `127.0.0.1:13001`. The overlay pins
`PAYMENT_MODE=mock` and `SMS_LIVE_ENABLED=false`; the base file keeps every
published port bound to `127.0.0.1` and points the app at `commerce-dev-postgres`.

Do not start the scheduler for this demo and do not use
`docker-compose.db.yml` (that is the separate Gate A harness).

## 3. Health check

```bash
curl -fsS http://127.0.0.1:13001/healthz
```

Expected: `{"status":"ok"}`.

## 4. Sign in from your own browser

Open:

- Storefront: <http://127.0.0.1:13001/>
- Admin: <http://127.0.0.1:13001/admin/login>

Sign in with the username and password you chose in step 1. Then open
<http://127.0.0.1:13001/admin/orders>. The existing paid demo order should still
be listed.

Use a private/incognito window if you want to verify a fresh session.

## 5. Safe restart

Restart the two development services without deleting data:

```bash
cd AI-Online-Business-Engine/commerce
docker compose -f docker-compose.yml -f docker-compose.demo.yml restart postgres commerce-web
```

## 6. Recreate only the web service after credential changes

```bash
cd AI-Online-Business-Engine/commerce
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --no-deps --force-recreate --wait commerce-web
```

This recreates only `commerce-dev-web`, leaves `commerce-dev-postgres` and its
volume untouched, and preserves orders, products and media.

If you need to stop the demo, use `docker compose -f docker-compose.yml -f docker-compose.demo.yml stop`.
Never use `docker compose down -v`: it removes the database volume.

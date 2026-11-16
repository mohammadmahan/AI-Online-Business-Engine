#!/usr/bin/env bash
# Local demo admin credentials — interactive, no secret in history or output.
#
#   cd commerce
#   bash scripts/setup-demo-admin.sh
#
# The password is read with echo disabled, hashed with the repository's own
# scrypt helper (via stdin, never an argument), and written to the gitignored
# commerce/.env together with a fresh session secret. Existing non-admin lines
# in .env are preserved. The password itself is never written to disk.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/.env"

read -r -p "Admin username [owner]: " admin_username
admin_username="${admin_username:-owner}"
if ! printf '%s' "$admin_username" | grep -Eq '^[A-Za-z0-9._-]{1,64}$'; then
  echo "Username must be 1-64 characters: letters, digits, dot, underscore or hyphen." >&2
  exit 1
fi

read -r -s -p "Admin password (input hidden): " admin_password
echo
read -r -s -p "Repeat password: " admin_password_confirm
echo
if [ -z "$admin_password" ]; then
  echo "A non-empty password is required." >&2
  exit 1
fi
if [ "${#admin_password}" -lt 12 ]; then
  echo "Use at least 12 characters for the local demo password." >&2
  exit 1
fi
if [ "$admin_password" != "$admin_password_confirm" ]; then
  echo "Passwords do not match." >&2
  exit 1
fi

password_hash="$(printf '%s' "$admin_password" | node "$ROOT/scripts/hash-admin-password.mjs")"
unset admin_password admin_password_confirm
session_secret="$(node -e "process.stdout.write(require('node:crypto').randomBytes(32).toString('hex'))")"

umask 077
tmp_file="$(mktemp "${ENV_FILE}.XXXXXX")"
if [ -f "$ENV_FILE" ]; then
  grep -vE '^(ADMIN_USERNAME|ADMIN_PASSWORD_HASH|ADMIN_SESSION_SECRET)=' "$ENV_FILE" >"$tmp_file" || true
fi
{
  printf 'ADMIN_USERNAME=%s\n' "$admin_username"
  printf 'ADMIN_PASSWORD_HASH=%s\n' "$password_hash"
  printf 'ADMIN_SESSION_SECRET=%s\n' "$session_secret"
} >>"$tmp_file"
mv "$tmp_file" "$ENV_FILE"
chmod 600 "$ENV_FILE" 2>/dev/null || true
unset password_hash session_secret

echo "Admin credentials written to commerce/.env (gitignored, owner-only where supported)."
echo "Recreate commerce-web so the values are applied:"
echo "  docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --no-deps --force-recreate --wait commerce-web"

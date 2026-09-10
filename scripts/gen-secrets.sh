#!/usr/bin/env bash
# Generate Authelia secrets idempotently (jwt / session / encryption + admin
# password hash). Writes a root-only env file consumed by the installer and the
# Authelia config renderer. Re-running never changes existing secrets.
#
#   SECRETS_FILE=/opt/caravan/secrets.env ADMIN_USER=admin bash scripts/gen-secrets.sh
set -euo pipefail

OUT="${SECRETS_FILE:-$(pwd)/secrets.env}"
ADMIN_USER="${ADMIN_USER:-admin}"
AUTHELIA_IMAGE="${AUTHELIA_IMAGE:-authelia/authelia:4.39.20}"

rand() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

if [ -f "$OUT" ] && grep -q '^JWT_SECRET=' "$OUT"; then
  echo "[secrets] $OUT already exists — keeping existing secrets"
  exit 0
fi

JWT_SECRET="$(rand)"
SESSION_SECRET="$(rand)"
ENCRYPTION_KEY="$(rand)"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(rand)}"

ADMIN_PASSWORD_HASH=""
if command -v docker >/dev/null 2>&1; then
  # authelia prints "Digest: $2b$12$..."; extract just the bcrypt hash.
  ADMIN_PASSWORD_HASH="$(docker run --rm "$AUTHELIA_IMAGE" \
    authelia crypto hash generate bcrypt --password "$ADMIN_PASSWORD" --no-confirm 2>/dev/null \
    | grep -oE '\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{53}' | tail -n1 || true)"
fi

umask 077
{
  echo "JWT_SECRET=$JWT_SECRET"
  echo "SESSION_SECRET=$SESSION_SECRET"
  echo "ENCRYPTION_KEY=$ENCRYPTION_KEY"
  echo "ADMIN_USER=$ADMIN_USER"
  if [ -n "$ADMIN_PASSWORD_HASH" ]; then
    echo "ADMIN_PASSWORD_HASH=$ADMIN_PASSWORD_HASH"
  fi
} > "$OUT"
chmod 600 "$OUT"

echo "[secrets] wrote $OUT (mode 600)"
echo "[secrets] admin user:     $ADMIN_USER"
echo "[secrets] admin password: $ADMIN_PASSWORD   <-- store it now; it is NOT saved"
if [ -z "$ADMIN_PASSWORD_HASH" ]; then
  echo "[secrets] WARN: docker not found — password hash not generated (installer will do it)"
fi

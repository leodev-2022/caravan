#!/usr/bin/env bash
# Project checks: python compile, ruff, shell syntax, shellcheck, YAML, secret scan.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "[check] python not found"; exit 1; }
echo "[check] python: $PY"

PYFILES="generate_caddy.py render.py status.py tools/apply_request.py tests"

echo "[check] python compile"
$PY -m compileall -q $PYFILES || fail=1

echo "[check] ruff"
RUFF=""
for cand in "ruff" "$PY -m ruff" "py -m ruff" "python -m ruff" "python3 -m ruff"; do
  if $cand --version >/dev/null 2>&1; then RUFF="$cand"; break; fi
done
if [ -n "$RUFF" ]; then
  $RUFF check $PYFILES || fail=1
else
  echo "  ruff not installed, skipping"
fi

echo "[check] shell syntax"
for f in install.sh caravan tools/*.sh scripts/*.sh; do
  [ -e "$f" ] || continue
  bash -n "$f" || fail=1
done

echo "[check] shellcheck"
if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -S warning install.sh caravan tools/*.sh scripts/*.sh || fail=1
else
  echo "  shellcheck not installed, skipping"
fi

echo "[check] YAML"
for f in conf/*.yaml conf/*.yml; do
  [ -e "$f" ] || continue
  $PY -c "import yaml,sys;yaml.safe_load(open(sys.argv[1]))" "$f" || fail=1
done

echo "[check] caravan.env"
if [ -f caravan.env ]; then
  # shellcheck disable=SC1091
  set -a; . ./caravan.env; set +a
  for k in DOMAIN EMAIL HUB_IP; do
    if [ -z "${!k:-}" ]; then echo "  missing $k"; fail=1; fi
  done
  echo "  DOMAIN=${DOMAIN:-<unset>} HUB_IP=${HUB_IP:-<unset>}"
else
  echo "  not present, skipping"
fi

echo "[check] secret scan"
if git grep -nE '(hskey-auth-[A-Za-z0-9_-]{20,}|[0-9]{8,10}:[A-Za-z0-9_-]{30,}|BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY)' \
     -- . ':!*.template.yml' ':!*.example' ':!*.md' 2>/dev/null; then
  echo "  ^ possible real secret"; fail=1
else
  echo "  clean"
fi

echo "[check] leak scan"
if [ -f .leak-patterns ]; then
  if git grep -nE -f .leak-patterns -- . 2>/dev/null; then
    echo "  ^ real infra value found in tracked files"; fail=1
  else
    echo "  clean"
  fi
else
  echo "  no .leak-patterns (local guard), skipping"
fi

if [ "$fail" -ne 0 ]; then echo "[check] FAILED"; exit 1; fi
echo "[check] OK"

#!/usr/bin/env bash
# CLI smoke tests for the `caravan` wrapper (no hub / no root required).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CARAVAN=(bash "$ROOT/caravan")
fails=0
pass() { printf '  ok   %s\n' "$*"; }
fail() { printf '  FAIL %s\n' "$*"; fails=$((fails + 1)); }

expect_rc() {
  local desc="$1" want="$2"
  shift 2
  "$@" >/dev/null 2>&1
  local got=$?
  if [ "$got" = "$want" ]; then pass "$desc (rc=$got)"; else fail "$desc (want $want, got $got)"; fi
}

expect_contains() {
  local desc="$1" needle="$2"
  shift 2
  local out
  out="$("$@" 2>&1)"
  case "$out" in
    *"$needle"*) pass "$desc" ;;
    *) fail "$desc (missing: $needle)" ;;
  esac
}

expect_rc "caravan (no args)" 0 "${CARAVAN[@]}"
expect_rc "caravan --help" 0 "${CARAVAN[@]}" --help
expect_rc "caravan help" 0 "${CARAVAN[@]}" help
expect_rc "caravan version" 0 "${CARAVAN[@]}" version
expect_rc "caravan bogus -> 1" 1 "${CARAVAN[@]}" bogus
expect_rc "token --help" 0 "${CARAVAN[@]}" token --help
expect_rc "token unknown -> 1" 1 "${CARAVAN[@]}" token --nope
expect_rc "install --help" 0 "${CARAVAN[@]}" install --help
expect_rc "uninstall --help" 0 "${CARAVAN[@]}" uninstall --help
expect_rc "add-node --help" 0 "${CARAVAN[@]}" add-node --help
expect_rc "remove-node --help" 0 "${CARAVAN[@]}" remove-node --help
expect_rc "backup --help" 0 "${CARAVAN[@]}" backup --help
expect_rc "restore --help" 0 "${CARAVAN[@]}" restore --help

expect_contains "version string" "caravan" "${CARAVAN[@]}" version
expect_contains "help shows Usage" "Usage" "${CARAVAN[@]}" --help
expect_contains "help lists backup" "backup" "${CARAVAN[@]}" --help

printf '\n[test_cli] %d failure(s)\n' "$fails"
[ "$fails" -eq 0 ]

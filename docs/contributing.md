# Contributing

Thanks for helping! Caravan is deliberately small — please keep changes focused
and verified.

## Dev setup
```bash
git clone <repo> && cd caravan
# you need: python3, shellcheck, ruff, and docker (optional, for integration)
make ci
```

Individual targets:
- `make check` — python compile, ruff, `bash -n`, shellcheck, YAML, secret + leak scan.
- `make test` — unit tests (`tests/`).
- `make test-cli` — CLI smoke tests.
- `make smoke` — render configs from examples; assert no real values leak.
- `make caddy-validate` — validate the rendered Caddyfile (needs docker).
- `make integration` — bring up the full stack and check health (needs docker).

## Conventions
- **Shell:** `set -euo pipefail`, idempotent, `bash -n` clean, shellcheck-clean.
- **Python (shipped):** stdlib only; keep it light (target: a $3 VPS).
- **No hardcoded domains/IPs** — read from config; use placeholders in examples.
- **Never commit secrets** — only `*.template.yml` and `*.example` files.
- **Never hand-edit generated files** — change the source of truth and regenerate.

## Repository layout
```
compose/            docker-compose stack
conf/               templates + example manifests
install.sh          hub installer (one command)
caravan             hub CLI
generate_caddy.py   renders Caddyfile + nodes.json from nodes.yaml
render.py           __PLACEHOLDER__ template renderer
status.py           portal (status + Telegram alerts)
tools/              node-join.sh, add/remove-node.sh, backup/restore.sh
scripts/            check.sh, doctor, uninstall, tests
tests/              unit tests
docs/               architecture, operations, security, faq, contributing
```

## Pull requests
1. Keep it small — one concern per PR.
2. Run `make ci` locally and make it green.
3. Keep the docs in sync when behavior changes.
4. No real infra values — the leak scan will catch them.

## Security
See [security.md](security.md). Please report vulnerabilities privately.

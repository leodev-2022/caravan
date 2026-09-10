# Changelog

All notable changes to Caravan are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-09-11

First public release.

### Added
- **Hub installer** (`install.sh`): Docker + Compose, secret generation, stack
  layout, config rendering, TLS modes (`--domain` / `--sslip` / `--self-signed`),
  idempotent re-run and `--update`.
- **Node onboarding** (`node-join.sh`): flag-based, mesh join, systemd unit,
  `--uninstall`/`--purge`, and capability-aware speech-to-text
  (`--stt-check` / `--stt` / `--stt-model`).
- **CLI** (`caravan`): `install`, `update`, `doctor`, `nodes list`, `token`,
  `add-node`, `remove-node`, `backup`, `restore`, `uninstall`, `version`.
- **Mesh** (headscale) + **SSO/TOTP** (Authelia) + **portal** dashboard with
  live status and Telegram alerts.
- **Tests & CI**: unit tests, CLI smoke tests, integration test (full stack),
  `make ci`.

### Security
- Default-deny perimeter (only 443 public), mesh-only nodes (no inbound),
  SSO + TOTP at the edge, root-only secrets, and a secret/leak scan in `make check`.

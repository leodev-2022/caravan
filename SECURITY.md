# Security Policy

## Supported versions
Caravan is pre-1.0; security fixes are applied to the latest `main`.

## Reporting a vulnerability
Please **do not** open a public issue for security problems.

Report privately via GitHub's **Security → Report a vulnerability** (Advisories),
or email the maintainers (see the repository profile). Include:
- a description and the impact,
- steps to reproduce (or a proof of concept),
- the affected version / commit.

We aim to acknowledge within a few days and to coordinate a fix and disclosure.

## Scope & hardening
See [docs/security.md](docs/security.md) for the threat model and the defaults
that ship with the stack. Never commit secrets — only `*.template.yml` /
`*.example` files are tracked, and `make check` scans for leaks.

.PHONY: check test test-cli smoke caddy-validate integration ci

check:
	@bash scripts/check.sh

test:
	@python3 -m unittest discover -s tests -v

test-cli:
	@bash scripts/test_cli.sh

smoke:
	@bash scripts/smoke.sh

caddy-validate:
	@bash scripts/caddy-validate.sh

integration:
	@bash scripts/test_integration.sh

ci: check test test-cli smoke caddy-validate integration

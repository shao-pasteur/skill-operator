PY := uv run python scripts/cli.py

.PHONY: build check test

build: ; $(PY) build

check:
	$(PY) check
	@if command -v claude >/dev/null 2>&1 && [ -f .claude-plugin/marketplace.json ]; then claude plugin validate .; fi

test: ; uv run pytest

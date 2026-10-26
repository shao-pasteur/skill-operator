PY := uv run python scripts/cli.py

.PHONY: build check test package new import hooks

build: ; $(PY) build

check:
	$(PY) check
	@if command -v claude >/dev/null 2>&1 && [ -f .claude-plugin/marketplace.json ]; then claude plugin validate .; fi

test: ; uv run pytest

package: ; $(PY) package --out dist
new: ; $(PY) new --category $(CATEGORY) --name $(NAME)
import: ; $(PY) import --src $(SRC) --category $(CATEGORY)
hooks: ; git config core.hooksPath .githooks

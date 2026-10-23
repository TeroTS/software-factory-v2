.PHONY: setup format format-check lint test coverage verify

setup:
	uv sync --locked

format:
	uv run --frozen ruff format .

format-check:
	uv run --frozen ruff format --check .

lint:
	uv run --frozen ruff check .

test:
	uv run --frozen pytest

coverage:
	./scripts/coverage

verify:
	$(MAKE) format-check
	$(MAKE) lint
	$(MAKE) coverage

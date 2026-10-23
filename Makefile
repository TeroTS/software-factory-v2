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
	node --experimental-test-coverage --test-coverage-include='**/sandbox_agent.mjs' \
		--test-coverage-lines=80 --test-coverage-branches=80 --test-coverage-functions=80 \
		--test-reporter=spec --test-reporter=lcov \
		--test-reporter-destination=stdout --test-reporter-destination=coverage.lcov \
		--test tests/wrapper-coverage.test.mjs

verify:
	$(MAKE) format-check
	$(MAKE) lint
	$(MAKE) coverage

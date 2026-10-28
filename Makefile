.PHONY: setup format format-check lint test coverage verify

setup:
	uv sync --locked
	npm ci

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
	npm run cdk -- synth --quiet
	bash -n infra/ec2/scripts/shared/prepare-storage.sh
	bash -n infra/ec2/scripts/factory/prepare-host.sh
	bash -n infra/ec2/scripts/factory/check-host.sh
	bash -n infra/ec2/scripts/factory/start-runner.sh
	bash -n infra/ec2/scripts/factory/stop-runner.sh
	bash -n infra/ec2/scripts/builder/bake-host.sh
	bash -n infra/ec2/scripts/builder/finalize-image.sh

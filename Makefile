.PHONY: check format lint test lock migrate agent-check agent-test

check: lint test agent-check

format:
	uv run ruff format
	uv run ruff check --fix

lint:
	uv run ruff format --check
	uv run ruff check
	uv run pyright

lock:
	uv lock --upgrade

test:
	docker compose run --rm test

migrate:
	docker compose run --rm web uv run python manage.py migrate

agent-check:
	uv run --project agent --directory agent ruff format --check
	uv run --project agent --directory agent ruff check
	uv run --project agent --directory agent pyright
	uv run --project agent --directory agent pytest

agent-test:
	uv run --project agent --directory agent pytest

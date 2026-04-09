.PHONY: test fix format pyright all-check run

test:
	uv run pytest tests -v --tb=short

format:
	uv run ruff format src tests

fix:
	uv run ruff check --fix src tests
	uv run ruff format src tests

pyright:
	uv run pyright src tests

all-check:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run pyright src tests
	uv run pytest tests -v --tb=short

run:
	uv run eval-banana run

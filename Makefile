.PHONY: install format lint type-check test quality project-info

install:
	python3 -m pip install --upgrade pip
	python3 -m pip install -e ".[dev]"

format:
	python3 -m ruff format .
	python3 -m ruff check . --fix

lint:
	python3 -m ruff check .
	python3 -m ruff format --check .

type-check:
	python3 -m mypy src

test:
	python3 -m pytest

quality: lint type-check test

project-info:
	python3 -m product_growth_intelligence project-info

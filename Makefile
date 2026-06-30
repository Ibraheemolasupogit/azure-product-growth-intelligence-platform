.PHONY: install format lint type-check test quality project-info generate-sample ingest-sample verify-ingestion-evidence analyse-funnels-sample verify-funnel-evidence

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

generate-sample:
	python3 -m product_growth_intelligence generate-data --profile sample --output-dir data/samples/nexaflow --overwrite

ingest-sample:
	python3 -m product_growth_intelligence ingest-batch --source data/samples/nexaflow --output-root /tmp/pgi-ingest-sample/interim --quality-root /tmp/pgi-ingest-sample/quality --run-id sample-ingestion --fixed-ingestion-time 2026-01-01T00:00:00Z --overwrite

verify-ingestion-evidence:
	python3 scripts/generate_ingestion_evidence.py
	git diff --exit-code -- docs/evidence/milestone-3

analyse-funnels-sample:
	python3 scripts/generate_funnel_evidence.py

verify-funnel-evidence:
	python3 scripts/generate_funnel_evidence.py
	git diff --exit-code -- docs/evidence/milestone-4

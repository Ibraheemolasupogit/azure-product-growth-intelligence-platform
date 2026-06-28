# Local Development Runbook

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
make install
```

## Quality Checks

```bash
make quality
```

This runs Ruff, Ruff format check, mypy, and pytest with coverage. The checks are local and do not require Azure credentials.

## Project Metadata Check

```bash
pgi project-info
python -m product_growth_intelligence project-info
```


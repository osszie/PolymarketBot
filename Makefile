PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PY := $(VENV)/bin/python

.PHONY: venv install install-dev test run web lint-help

venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv
	$(PIP) install -r requirements.txt -e .

install-dev: venv
	$(PIP) install -r requirements.txt -e ".[dev]"

test:
	$(PY) -m pytest tests/ -q

run:
	$(PY) -m polymarket_paper_bot --mode paper --iterations 3

web:
	$(PY) -m polymarket_paper_bot --mode web --host 127.0.0.1 --port 5050

lint-help:
	@echo "No linter configured; add ruff/mypy if desired."

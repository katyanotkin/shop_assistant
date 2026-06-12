PYTHON=python
VENV=.venv
UV=uv

.DEFAULT_GOAL := help

.PHONY: help install run run-dry list add test lint web local-run

## Show available commands
help:
	@echo ""
	@echo "Shop Assistant"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'
	@echo ""

## Install dependencies into .venv
install: ## Install dependencies
	$(UV) venv $(VENV) --python 3.12
	$(UV) pip install -e ".[dev]" --python $(VENV)/bin/python || \
	$(UV) pip install -e . --python $(VENV)/bin/python

## Run all active searches
run: ## Run all active searches
	PYTHONPATH=. $(PYTHON) run.py run

## Run one search (SEARCH=name)
run-one: ## Run one search: make run-one SEARCH=wax_coat
	PYTHONPATH=. $(PYTHON) run.py run --search $(SEARCH)

## Dry-run: search and print, no save or notify
dry-run: ## Dry-run one search: make dry-run SEARCH=wax_coat
	PYTHONPATH=. $(PYTHON) run.py run --search $(SEARCH) --dry-run

## List searches in Firestore
list: ## List all searches
	PYTHONPATH=. $(PYTHON) run.py list

## Add/update a search from a JSON file (FILE=searches/wax_coat.json)
add: ## Add search: make add FILE=searches/wax_coat.json
	PYTHONPATH=. $(PYTHON) run.py add $(FILE)

## Add the example wax coat search
add-example: ## Add example wax_coat search to Firestore
	PYTHONPATH=. $(PYTHON) run.py add searches/wax_coat.json

## Run test suite
test: ## Run tests
	PYTHONPATH=. $(VENV)/bin/pytest tests/ -q --tb=short

## Lint
lint: ## Run ruff
	ruff check shop_assistant/ run.py

## Start local web UI (http://localhost:8000)
web: ## Start web UI dev server
	PYTHONPATH=. $(PYTHON) -m uvicorn web.main:app --reload --port 8000

## Install web deps and start local web UI (http://localhost:8000)
local-run: ## Install web deps then start web UI
	$(VENV)/bin/pip install -q fastapi uvicorn
	PYTHONPATH=. $(VENV)/bin/python -m uvicorn web.main:app --reload --port 8000

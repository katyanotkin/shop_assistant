PYTHON=python
VENV=.venv

GCP_REGION=us-east1
GCP_PROJECT?=knotmem26
GCP_REPOSITORY=shop-assistant
GCP_SERVICE=shop-assistant-web
DOMAIN=shopassistant.verbboard.com
PROD_URL?=https://$(DOMAIN)

IMAGE_TAG=$(shell git rev-parse --short HEAD)
GCP_IMAGE=$(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/$(GCP_REPOSITORY)/web:$(IMAGE_TAG)

.DEFAULT_GOAL := help

.PHONY: help install run run-one dry-run list add add-example test lint web local-run \
	gcp-check gcp-auth gcp-build gcp-deploy gcp-map gcp-open apply-trigger validate-prod

## Show available commands
help:
	@echo ""
	@echo "Shop Assistant"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-22s %s\n", $$1, $$2}'
	@echo ""

## Install dependencies into .venv
install: ## Install dependencies
	python3.12 -m venv $(VENV)
	$(VENV)/bin/pip install -e .

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

## Add/update a search from a JSON file
add: ## Add search: make add FILE=searches/wax_coat.json
	PYTHONPATH=. $(PYTHON) run.py add $(FILE)

## Add the example wax coat search
add-example: ## Add example wax_coat search to Firestore
	PYTHONPATH=. $(PYTHON) run.py add searches/wax_coat.json

## Run test suite
test: ## Run tests
	PYTHONPATH=. $(VENV)/bin/pytest tests/ -q --tb=short

## Smoke-test the live deployment (PROD_URL defaults to https://$(DOMAIN))
validate-prod: ## Smoke-test production: make validate-prod [PROD_URL=https://...]
	PROD_URL=$(PROD_URL) PYTHONPATH=. $(VENV)/bin/pytest tests/test_smoke.py -v

## Lint
lint: ## Run ruff
	$(VENV)/bin/ruff check core/ web/ run.py

## Start web UI dev server (http://localhost:8000)
web: ## Start web UI dev server
	PYTHONPATH=. $(PYTHON) -m uvicorn web.main:app --reload --port 8000

## Install web deps and start web UI locally
local-run: ## Install web deps then start web UI
	$(VENV)/bin/pip install -q fastapi uvicorn
	PYTHONPATH=. $(VENV)/bin/python -m uvicorn web.main:app --reload --port 8000

## GCP: validate GCP_PROJECT is set
gcp-check: ## GCP: validate required variables
	@test -n "$(GCP_PROJECT)" || (echo "ERROR: set GCP_PROJECT, e.g. make gcp-deploy GCP_PROJECT=my-project" && exit 1)

## GCP: configure Docker auth for Artifact Registry
gcp-auth: gcp-check ## GCP: configure docker auth for Artifact Registry
	gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev

## GCP: build and push Docker image
gcp-build: gcp-check gcp-auth ## GCP: build and push web image (tag = git SHA)
	@echo "Building $(GCP_IMAGE)"
	docker build -f Dockerfile.web -t $(GCP_IMAGE) .
	docker push $(GCP_IMAGE)
	@echo "Pushed: $(GCP_IMAGE)"

## GCP: build, push, and deploy web UI to Cloud Run
gcp-deploy: gcp-build ## GCP: build + push + deploy to Cloud Run
	gcloud run deploy $(GCP_SERVICE) \
		--image=$(GCP_IMAGE) \
		--region=$(GCP_REGION) \
		--platform=managed \
		--allow-unauthenticated \
		--project=$(GCP_PROJECT) \
		--set-env-vars=GOOGLE_CLOUD_PROJECT=$(GCP_PROJECT) \
		--set-secrets=ADMIN_PASSWORD=shop-assistant-admin-password:latest
	@echo "Deployed: $(GCP_SERVICE)"

## GCP: print deployed service URL
gcp-open: gcp-check ## GCP: print Cloud Run service URL
	@gcloud run services describe $(GCP_SERVICE) \
		--region=$(GCP_REGION) \
		--project=$(GCP_PROJECT) \
		--format='value(status.url)'

## GCP: map shopassistant.verbboard.com to Cloud Run service (one-time)
gcp-map: gcp-check ## GCP: map $(DOMAIN) to Cloud Run service (one-time)
	gcloud beta run domain-mappings create \
		--service=$(GCP_SERVICE) \
		--domain=$(DOMAIN) \
		--region=$(GCP_REGION) \
		--project=$(GCP_PROJECT)

## GCP: import/update Cloud Build trigger (region=us-east1)
apply-trigger: gcp-check ## GCP: import/update Cloud Build trigger (region=us-east1)
	gcloud builds triggers import \
		--source=cloudbuild-trigger.yaml \
		--region=$(GCP_REGION) \
		--project=$(GCP_PROJECT)

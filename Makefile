.DEFAULT_GOAL := check
UV ?= uv
PRODUCER_ROOT ?= ../datamimic-ee

.PHONY: check test lint typecheck fixtures
check: lint typecheck test

test:
	PLEDGE_PRODUCER_ROOT="$(abspath $(PRODUCER_ROOT))" $(UV) run --locked python -m pytest -q

lint:
	$(UV) run --locked ruff format --check src tests fixtures/reproduce_milestone1.py
	$(UV) run --locked ruff check src tests fixtures/reproduce_milestone1.py

typecheck:
	$(UV) run --locked mypy src/pledge

fixtures:
	$(UV) run --locked python fixtures/reproduce_milestone1.py --producer-root "$(PRODUCER_ROOT)" $(if $(OUTPUT),--output "$(OUTPUT)")

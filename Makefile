.DEFAULT_GOAL := check
UV ?= uv

.PHONY: check test lint typecheck fixtures build smoke release-check
check: lint typecheck test

release-check: check build smoke

test:
	$(UV) run --locked python -m pytest -q

lint:
	$(UV) run --locked ruff format --check src tests fixtures/reproduce_milestone1.py
	$(UV) run --locked ruff check src tests fixtures/reproduce_milestone1.py

typecheck:
	$(UV) run --locked mypy src/archkeel

fixtures:
	$(UV) run --locked python fixtures/reproduce_milestone1.py $(if $(OUTPUT),--output "$(OUTPUT)")

# Twine validates PyPI metadata; it is a build-only tool.
build:
	$(UV) build --no-sources --clear
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/*

smoke:
	$(UV) run --isolated --no-project --with dist/*.whl tests/smoke_test.py
	$(UV) run --isolated --no-project --with dist/*.tar.gz tests/smoke_test.py

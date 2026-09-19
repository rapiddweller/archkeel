.DEFAULT_GOAL := check
UV ?= uv

.PHONY: check test lint typecheck fixtures self-observation demo demo-onboarding loop-figure demo-screenshots build smoke release-check
check: lint typecheck test

release-check: check build smoke

test:
	$(UV) run --locked python -m pytest -q

LINT_PATHS := src tests tools/terminal_svg.py tools/interface_profile.py tools/mermaid_blocks.py \
	tools/onboarding_svg.py \
	fixtures/reproduce_milestone1.py fixtures/reproduce_onboarding.py fixtures/reproduce_self.py \
	fixtures/architecture_demo.py fixtures/demo_catalog_*.py

lint:
	$(UV) run --locked ruff format --check $(LINT_PATHS)
	$(UV) run --locked ruff check $(LINT_PATHS)

typecheck:
	$(UV) run --locked mypy src/archkeel

fixtures:
	$(UV) run --locked python fixtures/reproduce_milestone1.py $(if $(OUTPUT),--output "$(OUTPUT)")

self-observation:
	$(UV) run --locked python -m fixtures.reproduce_self

demo:
	@$(UV) run --locked python fixtures/reproduce_milestone1.py $(if $(OUTPUT),--output "$(OUTPUT)") --summary

demo-onboarding:
	@$(UV) run --locked python -m fixtures.reproduce_onboarding

# The figure is derived from the run above, so a test compares it with a fresh render.
loop-figure:
	@$(UV) run --locked python -m tools.onboarding_svg docs/assets/archkeel-onboarding-loop.svg

demo-screenshots:
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(MAKE) demo OUTPUT="$(OUTPUT)"
	@set -e; for case in A B C; do \
		firefox --headless --no-remote --window-size 1440,1000 \
		  --screenshot "$(OUTPUT)/$$case-check-1440x1000.png" \
		  "file://$(abspath $(OUTPUT))/$$case-check.stdout.check.html"; \
	done
	@firefox --headless --no-remote --window-size 375,2400 \
	  --screenshot "$(OUTPUT)/A-check-375x2400.png" \
	  "file://$(abspath $(OUTPUT))/A-check.stdout.check.html"
	@$(UV) run --locked python tools/terminal_svg.py "$(OUTPUT)"
	@printf 'Screenshots: %s\n' "$(abspath $(OUTPUT))"

# Twine validates PyPI metadata; it is a build-only tool.
build:
	$(UV) build --no-sources --clear
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/*

smoke:
	$(UV) run --isolated --no-project --with dist/*.whl tests/smoke_test.py
	$(UV) run --isolated --no-project --with dist/*.tar.gz tests/smoke_test.py

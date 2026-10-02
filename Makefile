.DEFAULT_GOAL := check
UV ?= uv

.PHONY: gate check test lint typecheck self-validate fixtures self-observation demo demo-github github-pr-report demo-onboarding demo-dart demo-architecture loop-figure demo-screenshots browser-install report-browser plugin build smoke release-check
check: lint typecheck test

gate: release-check self-validate

release-check: check build smoke

self-validate:
	$(UV) run --locked archkeel validate --root . --baseline architecture-baseline.json --json

test:
	$(UV) run --locked python -m pytest -q

LINT_PATHS := src tests tools/terminal_svg.py tools/interface_profile.py tools/mermaid_blocks.py \
	tools/onboarding_svg.py tools/report_browser.py tools/package_plugin.py tools/github_pr_report.py \
	fixtures/reproduce_milestone1.py fixtures/reproduce_onboarding.py fixtures/reproduce_self.py \
	fixtures/reproduce_dart.py fixtures/reproduce_github.py \
	fixtures/architecture_demo.py fixtures/demo_catalog_*.py

lint:
	$(UV) run --locked ruff format --check $(LINT_PATHS)
	$(UV) run --locked ruff check $(LINT_PATHS)

typecheck:
	$(UV) run --locked mypy src/archkeel tools/github_pr_report.py

fixtures:
	$(UV) run --locked python fixtures/reproduce_milestone1.py $(if $(OUTPUT),--output "$(OUTPUT)")

self-observation:
	$(UV) run --locked python -m fixtures.reproduce_self

demo:
	@$(UV) run --locked python fixtures/reproduce_milestone1.py $(if $(OUTPUT),--output "$(OUTPUT)") --summary

demo-github:
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(UV) run --locked python -m fixtures.reproduce_github --output "$(OUTPUT)"

github-pr-report:
	@$(UV) run --locked python -m tools.github_pr_report \
		--repository "$(REPOSITORY)" --pull-request "$(PULL_REQUEST)" \
		--base "$(BASE)" --head "$(HEAD)" --output "$(OUTPUT)"

demo-onboarding:
	@$(UV) run --locked python -m fixtures.reproduce_onboarding

demo-dart:
	@$(UV) run --locked python -m fixtures.reproduce_dart

demo-architecture:
	@test -n "$(VARIANT)" || { echo "VARIANT is required"; exit 2; }
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(UV) run --locked python -m fixtures.architecture_demo --replay "$(VARIANT)" --output "$(OUTPUT)"

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
	@$(UV) run --locked python -m tools.terminal_svg "$(OUTPUT)"
	@printf 'Screenshots: %s\n' "$(abspath $(OUTPUT))"

PLAYWRIGHT_VERSION ?= 1.62.0

browser-install:
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m playwright install --with-deps chromium

plugin:
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	$(UV) run --locked python -m tools.package_plugin "$(OUTPUT)"

report-browser:
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m pytest -q tests/test_actual_target_diff_acceptance.py tests/test_target_diagram_acceptance.py tests/test_target_hierarchy_independent_acceptance.py tests/test_consistent_explorer_acceptance.py tests/test_compact_report_headers.py tests/test_frame_edge_semantics.py tests/test_exact_module_target_leaf.py
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m tools.report_browser $(if $(OUTPUT),--output "$(OUTPUT)")

# Twine validates PyPI metadata; it is a build-only tool.
build:
	$(UV) build --no-sources --clear
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/*

smoke:
	$(UV) run --isolated --no-project --with dist/*.whl tests/smoke_test.py
	$(UV) run --isolated --no-project --with dist/*.tar.gz tests/smoke_test.py

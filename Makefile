.DEFAULT_GOAL := check
UV ?= uv

.PHONY: against gate ci ci-check ci-core-check ci-report-check ci-typescript ci-artifacts-clean mermaid check test collector-safety lint typecheck self-validate fixtures self-observation demo demo-github github-pr-report demo-onboarding demo-dart demo-typescript demo-snapshot-check demo-architecture demo-uml loop-figure demo-screenshots browser-install report-browser plugin plugin-directory build smoke release-check rule-yield architecture-graph-schema report-timing

check: lint typecheck test

# These stages consume the previous stage's success, even with make -j.
.NOTPARALLEL: gate release-check ci ci-check ci-core-check ci-report-check

gate: $(if $(strip $(BASE)),against,self-validate) release-check

release-check: check build smoke

ci: ci-check mermaid

ci-check: ci-artifacts-clean ci-core-check ci-report-check

ci-core-check: gate ci-typescript

ci-report-check: report-timing browser-install report-browser

ci-typescript: OUTPUT := test-artifacts/typescript-demo
ci-typescript: demo-typescript

ci-artifacts-clean:
	rm -rf test-artifacts/typescript-demo test-artifacts/report-browser test-artifacts/report-timing

mermaid:
	@set -eu; mermaid_dir=$$(mktemp -d); \
		trap 'rm -rf "$$mermaid_dir"' 0; \
		python3 tools/mermaid_blocks.py --write "$$mermaid_dir"; \
		printf '{"args": ["--no-sandbox"]}\n' > "$$mermaid_dir/puppeteer-config.json"; \
		fail=0; \
		for mmd in "$$mermaid_dir"/*.mmd; do \
			[ -f "$$mmd" ] || continue; \
			number=$$(basename "$$mmd" .mmd); \
			location=$$(awk -F'\t' -v n="$$number" '$$1 == n { print $$2 }' "$$mermaid_dir/index.txt"); \
			if ! npx --yes @mermaid-js/mermaid-cli@11.17.0 -p "$$mermaid_dir/puppeteer-config.json" -i "$$mmd" -o "$$mmd.svg"; then \
				echo "::error::$$location: mermaid-cli failed to render this block"; \
				fail=1; \
			fi; \
		done; \
		exit "$$fail"

against: BASE ?= origin/main
against:
	$(UV) run --locked python -m tools.against --base "$(BASE)"

self-validate:
	$(UV) run --locked archkeel validate --root . --baseline architecture-baseline.json --json

test: typescript-adapter
	$(UV) run --locked python -m pytest -n 2 --dist=loadfile --max-worker-restart=0 \
		-q --durations=20 --junitxml=test-artifacts/pytest/results.xml

collector-safety:
	$(UV) run --locked python -m pytest -q tests/test_collection_protocol.py \
		tests/test_collection_process.py tests/test_collection_runtime_gate.py \
		tests/test_runtime.py tests/test_source_trust_boundary.py \
		tests/test_collector_interrupt.py tests/test_windows_launcher_startup.py \
		tests/test_collector_safety_acceptance.py tests/test_collector_liveness_observer.py \
		tests/test_inheritance_proof_transport.py
.PHONY: typescript-adapter typescript-differential
typescript-adapter:
	$(MAKE) -C packages/typescript-adapter install pack

# The Node adapter stays the reference until the in-package frontend has run in CI beside it.
typescript-differential: typescript-adapter
	ARCHKEEL_DIFFERENTIAL_OUTPUT="$(or $(OUTPUT),test-artifacts/typescript-differential)" \
		$(UV) run --locked python -m pytest -q tests/test_typescript_differential.py

LINT_PATHS := src tests tools/terminal_svg.py tools/interface_profile.py tools/rule_yield.py tools/mermaid_blocks.py tools/ci_changes.py \
	tools/classify_unresolved.py tools/onboarding_svg.py tools/report_browser.py tools/package_plugin.py tools/github_pr_report.py tools/against.py \
	fixtures/reproduce_milestone1.py fixtures/reproduce_onboarding.py fixtures/reproduce_self.py \
	fixtures/reproduce_dart.py fixtures/reproduce_snapshot_check.py fixtures/consume_result.py fixtures/reproduce_github.py \
	fixtures/reproduce_typescript.py fixtures/typescript_differential.py fixtures/typescript_scenarios.py \
	fixtures/architecture_demo.py fixtures/demo_catalog_*.py \
	tools/architecture_graph_schema.py tools/report_timing.py

REPORT_MAX_SECONDS ?= 90
report-timing:
	$(UV) run --locked python -m tools.report_timing --max-seconds "$(REPORT_MAX_SECONDS)"

architecture-graph-schema:
	$(UV) run --locked python -m tools.architecture_graph_schema schema/architecture-graph.schema.json --contract schema/architecture-contract.schema.json --comparison schema/architecture-comparison.schema.json --report schema/architecture-report.schema.json --source-inventory schema/source-member-inventory.schema.json --source-profile schema/architecture-ir-python-decoded.schema.json --projection schema/architecture-projection.schema.json --command schema/architecture-command.schema.json

lint:
	$(UV) run --locked ruff format --check $(LINT_PATHS)
	$(UV) run --locked ruff check $(LINT_PATHS)

typecheck:
	$(UV) run --locked mypy src/archkeel tools/github_pr_report.py tools/against.py tools/architecture_graph_schema.py tools/report_timing.py tools/ci_changes.py

fixtures:
	$(UV) run --locked python fixtures/reproduce_milestone1.py $(if $(OUTPUT),--output "$(OUTPUT)")

self-observation:
	$(UV) run --locked python -m fixtures.reproduce_self

rule-yield:
	@test -n "$(ROOT)" || { echo "ROOT is required"; exit 2; }
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	$(UV) run --locked python -m tools.rule_yield --root "$(ROOT)" --output "$(OUTPUT)"

demo:
	@$(UV) run --locked python fixtures/reproduce_milestone1.py $(if $(OUTPUT),--output "$(OUTPUT)") --summary

demo-github:
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(UV) run --locked python -m fixtures.reproduce_github --output "$(OUTPUT)"

github-pr-report:
	@$(UV) run --locked python -m tools.github_pr_report \
		--repository "$(REPOSITORY)" --pull-request "$(PULL_REQUEST)" \
		--base "$(BASE)" --head "$(HEAD)" --output "$(OUTPUT)" \
		$(if $(ROOT),--root "$(ROOT)") $(if $(INITIAL_RUN),--initial-run "$(INITIAL_RUN)") \
		$(if $(EXPECTATION_COMMIT),--expectation-commit "$(EXPECTATION_COMMIT)") \
		$(if $(EXPECTED),--expected "$(EXPECTED)") $(if $(EXPECTED_DIGEST),--expected-digest "$(EXPECTED_DIGEST)")

demo-onboarding:
	@$(UV) run --locked python -m fixtures.reproduce_onboarding

demo-dart:
	@$(UV) run --locked python -m fixtures.reproduce_dart

demo-snapshot-check:
	@$(UV) run --locked python -m fixtures.reproduce_snapshot_check

demo-typescript:
	@$(UV) run --locked python -m fixtures.reproduce_typescript $(if $(OUTPUT),--output "$(OUTPUT)")

demo-architecture:
	@test -n "$(VARIANT)" || { echo "VARIANT is required"; exit 2; }
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(UV) run --locked python -m fixtures.architecture_demo --replay "$(VARIANT)" --output "$(OUTPUT)"

demo-uml: typescript-adapter
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(MAKE) demo-architecture VARIANT=uml-match OUTPUT="$(OUTPUT)/python.json"
	@$(MAKE) demo-architecture VARIANT=uml-complete OUTPUT="$(OUTPUT)/python-complete.json"
	@$(MAKE) demo-architecture VARIANT=uml-dart OUTPUT="$(OUTPUT)/dart.json"
	@$(MAKE) demo-architecture VARIANT=uml-typescript OUTPUT="$(OUTPUT)/typescript.json"

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

plugin-directory:
	@mkdir -p build plugins/archkeel
	@set -e; stage=$$(mktemp -d build/plugin.XXXXXX); \
		$(MAKE) plugin OUTPUT="$$stage/archkeel" && \
		cp -R "$$stage/archkeel/." plugins/archkeel/

report-browser:
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m pytest -q tests/test_*report*.py tests/test_*uml*.py tests/test_*flow*.py tests/test_secondary_table_acceptance.py tests/test_legacy_graph_rendering.py tests/test_diff_import_rendering.py
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m tools.report_browser $(if $(OUTPUT),--output "$(OUTPUT)")

# Twine validates PyPI metadata; it is a build-only tool.
build:
	$(UV) build --no-sources --clear
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/*

smoke:
	$(UV) run --isolated --no-project --with dist/*.whl tests/smoke_test.py
	$(UV) run --isolated --no-project --with dist/*.tar.gz tests/smoke_test.py

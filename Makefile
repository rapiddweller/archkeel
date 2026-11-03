.DEFAULT_GOAL := check
UV ?= uv
DART_EXECUTABLE ?= dart
FLUTTER_EXECUTABLE ?= flutter

.PHONY: demos against gate full-test ci ci-check ci-core-check ci-pr-check ci-pr-static ci-pr-report-check pr-test pr-report-test ci-typescript ci-artifacts-clean mermaid check test collector-safety python-compat typescript-native typescript-compiler-check dart-test lint typecheck self-validate self-observation demo demo-onboarding demo-dart demo-typescript demo-architecture demo-uml demo-screenshots browser-install report-browser-tests report-pages plugin plugin-release build smoke release-check architecture-graph-schema report-timing flutter-demo-check browser-runtime-install browser-runtime-generate browser-runtime-check typescript-libs-check browser-graph-generate browser-graph-check browser-architecture-check

# SKIP_TESTS=1: skip the test suite here; Full verification runs it in area jobs (make full-test).
check: lint typecheck browser-architecture-check $(if $(strip $(SKIP_TESTS)),,test)

# These stages consume the previous stage's success, even with make -j.
.NOTPARALLEL: gate full-test release-check ci ci-check ci-core-check ci-pr-check ci-pr-static ci-pr-report-check

gate: $(if $(strip $(BASE)),against,self-validate) release-check

release-check: check build smoke

ci: ci-check mermaid

ci-check: ci-artifacts-clean ci-core-check report-timing

ci-core-check: PYTEST_STOP := --maxfail=1
ci-core-check: gate typescript-compiler-check browser-graph-check ci-typescript browser-runtime-check typescript-libs-check

# One area of the full suite (tests/areas.py); Full verification runs every area in parallel.
full-test: TEST_WORKERS = 4
full-test: browser-runtime-install test

ci-pr-check: ci-pr-static pr-test

ci-pr-static: $(if $(strip $(BASE)),against,self-validate) lint typecheck browser-architecture-check

ci-pr-report-check: browser-runtime-check browser-graph-check pr-report-test

pr-test: browser-runtime-install
	$(UV) run --locked python -m pytest -n 4 --dist=loadgroup --max-worker-restart=0 \
		-q --durations=10 --junitxml=test-artifacts/pytest/pr-core.xml --selection=pr \
		$(if $(AREA),--area="$(AREA)",)

pr-report-test:
	$(UV) run --locked python -m pytest -n 2 --dist=loadfile --max-worker-restart=0 -q \
		--junitxml=test-artifacts/pytest/pr-report.xml --selection=pr-report

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
	@mkdir -p test-artifacts/validation
	@$(UV) run --locked archkeel validate --root . --baseline architecture-baseline.json --json > test-artifacts/validation/result.json || { cat test-artifacts/validation/result.json; exit 1; }
	@python3 -c 'import json; d=json.load(open("test-artifacts/validation/result.json")); print("Architecture rules: %s; diagnostics: %s; full result: test-artifacts/validation/result.json" % (d["declared_rules"], len(d["diagnostics"])))'

TEST_WORKERS ?= 2

test:
	$(UV) run --locked $(PYTEST_EXTRA) python -m pytest -n $(TEST_WORKERS) --dist=loadgroup --max-worker-restart=0 \
		-q $(PYTEST_STOP) --durations=20 --junitxml=test-artifacts/pytest/results.xml \
		$(if $(AREA),--area="$(AREA)",)

# Each test that needs Python 3.12 or later, and the files that cover version differences (#724).
python-compat:
	$(UV) run --locked python -m pytest -n $(TEST_WORKERS) --dist=loadfile --max-worker-restart=0 \
		-q --durations=10 --selection=python-compat

collector-safety:
	$(UV) run --locked python -m pytest -q --selection=collector-safety
typescript-compiler-check:
	npx --yes --package typescript@5.9.3 tsc --noEmit --project fixtures/H-uml-typescript/tsconfig.json

# Python implementation architecture is covered by make test, once on Linux in CI.
typescript-native: browser-runtime-install
	$(UV) run --locked python -m pytest -n $(TEST_WORKERS) --dist=loadfile --max-worker-restart=0 \
		-q --durations=10 --selection=typescript-native

dart-test:
	$(UV) run --locked python -m pytest -n $(TEST_WORKERS) --dist=worksteal --max-worker-restart=0 \
		-q --durations=10 --selection=dart

LINT_PATHS := src tests tools/mermaid_blocks.py \
	tools/report_pages.py tools/package_plugin.py tools/against.py \
	fixtures/reproduce_milestone1.py fixtures/reproduce_onboarding.py \
	fixtures/reproduce_dart.py fixtures/reproduce_snapshot_check.py fixtures/consume_result.py \
	fixtures/reproduce_typescript.py \
	fixtures/architecture_demo.py fixtures/demo_catalog_*.py \
	tools/architecture_graph_schema.py tools/report_timing.py tools/browser_runtime.py tools/browser_graph_protocol.py tools/browser_architecture.py tools/publish_release.py tools/typescript_libs.py

# The same commit measured 80-96s on hosted runners; allow for runner noise.
REPORT_MAX_SECONDS ?= 190
report-timing:
	$(UV) run --locked python -m tools.report_timing --max-seconds "$(REPORT_MAX_SECONDS)"

# Builds the demo gallery in test-artifacts/pages; Full publishes this same build.
demos:
	rm -rf test-artifacts/pages
	$(UV) run --locked python -m tools.report_pages

report-pages: report-timing demos
	cp test-artifacts/report-timing/architecture.json test-artifacts/report-timing/architecture.report.html \
		test-artifacts/report-timing/architecture.detail*.html test-artifacts/pages/

architecture-graph-schema:
	$(UV) run --locked python -m tools.architecture_graph_schema schema/architecture-graph.schema.json --contract schema/architecture-contract.schema.json --contract schema/architecture-contract-3.0.schema.json --contract schema/architecture-contract-3.1.schema.json --contract schema/architecture-contract-3.2.schema.json --contract schema/architecture-contract-3.3.schema.json --contract schema/architecture-contract-3.4.schema.json --contract schema/architecture-contract-3.5.schema.json --contract schema/architecture-contract-3.6.schema.json --contract schema/architecture-contract-3.7.schema.json --contract schema/architecture-contract-3.8.schema.json --contract schema/architecture-contract-3.9.schema.json --contract schema/architecture-contract-3.10.schema.json --contract schema/architecture-contract-3.11.schema.json --contract schema/architecture-contract-3.12.schema.json --contract schema/architecture-contract-3.13.schema.json --contract schema/architecture-contract-3.14.schema.json --comparison schema/architecture-comparison.schema.json --report schema/architecture-report.schema.json --source-inventory schema/source-member-inventory.schema.json --source-profile schema/architecture-ir-python-decoded.schema.json --projection schema/architecture-projection.schema.json --command schema/architecture-command-2.0.schema.json --view-spec schema/view-spec.schema.json --view-check schema/view-check.schema.json

lint:
	$(UV) run --locked ruff format --check $(LINT_PATHS)
	$(UV) run --locked ruff check $(LINT_PATHS)

typecheck:
	$(UV) run --locked mypy src/archkeel tools/against.py tools/architecture_graph_schema.py tools/report_timing.py tools/browser_architecture.py tools/publish_release.py

self-observation:
	$(UV) run --locked archkeel report --root . --output test-artifacts/self-observation/architecture.json

demo:
	@$(UV) run --locked python fixtures/reproduce_milestone1.py $(if $(OUTPUT),--output "$(OUTPUT)") --summary

demo-onboarding:
	@$(UV) run --locked python -m fixtures.reproduce_onboarding

demo-dart:
	@$(UV) run --locked python -m fixtures.reproduce_dart

flutter-demo-check:
	@command -v "$(FLUTTER_EXECUTABLE)" >/dev/null 2>&1 || test -x "$(FLUTTER_EXECUTABLE)" || { echo "Flutter SDK not found: $(FLUTTER_EXECUTABLE)"; exit 2; }
	@command -v "$(DART_EXECUTABLE)" >/dev/null 2>&1 || test -x "$(DART_EXECUTABLE)" || { echo "Dart SDK not found: $(DART_EXECUTABLE)"; exit 2; }
	"$(FLUTTER_EXECUTABLE)" --version --machine
	"$(DART_EXECUTABLE)" --version
	cd fixtures/I-flutter-shop && "$(FLUTTER_EXECUTABLE)" pub get
	"$(DART_EXECUTABLE)" format --output=none --set-exit-if-changed fixtures/I-flutter-shop/lib fixtures/I-flutter-shop/test
	cd fixtures/I-flutter-shop && "$(FLUTTER_EXECUTABLE)" analyze
	cd fixtures/I-flutter-shop && "$(FLUTTER_EXECUTABLE)" test
	cd fixtures/I-flutter-shop && "$(FLUTTER_EXECUTABLE)" build web --output "$(abspath test-artifacts/flutter-demo/web)"

demo-typescript:
	@$(UV) run --locked python -m fixtures.reproduce_typescript $(if $(OUTPUT),--output "$(OUTPUT)")

demo-architecture:
	@test -n "$(VARIANT)" || { echo "VARIANT is required"; exit 2; }
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(UV) run --locked python -m fixtures.architecture_demo --replay "$(VARIANT)" --output "$(OUTPUT)"

demo-uml: typescript-compiler-check
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(UV) run --locked python -m fixtures.architecture_demo --uml-suite --output "$(OUTPUT)"

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
	@printf 'Screenshots: %s\n' "$(abspath $(OUTPUT))"

PLAYWRIGHT_VERSION ?= 1.62.0

browser-install:
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m playwright install --with-deps chromium

plugin:
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	$(UV) run --locked python -m tools.package_plugin "$(OUTPUT)"

plugin-release:
	@test -n "$(VERSION)" || { echo "VERSION is required"; exit 2; }
	$(UV) run --locked python -m tools.package_plugin --release-version "$(VERSION)" --expected-version "$(VERSION)" "build/plugin-release/archkeel-plugin-$(VERSION)"
	$(UV) run --locked python -m tools.package_plugin --check --release-version "$(VERSION)" --expected-version "$(VERSION)" "build/plugin-release/archkeel-plugin-$(VERSION).zip"

report-browser-tests: browser-install
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m pytest -m browser -n 2 --dist=loadfile --max-worker-restart=0 -q

# Twine validates PyPI metadata; it is a build-only tool.
build:
	$(UV) build --no-sources --clear
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/*

smoke:
	$(UV) run --isolated --no-project --with dist/*.whl tests/smoke_test.py
	$(UV) run --isolated --no-project --with dist/*.tar.gz tests/smoke_test.py

# Development publication only; reports and Python package builds load committed assets.
browser-runtime-install:
	npm ci --prefix tools/browser-runtime --ignore-scripts --no-audit --no-fund
	$(UV) run --locked python -m tools.browser_runtime --prepare-dependencies

browser-runtime-generate: browser-runtime-install
	uv run --locked python -m tools.browser_runtime

browser-runtime-check: browser-runtime-install
	uv run --locked mypy --strict tools/browser_runtime.py
	uv run --locked python -m tools.browser_runtime --check
	uv run --locked python -m pytest -q tests/test_flow_runtime_publication.py

typescript-libs-check: browser-runtime-install
	$(UV) run --locked mypy --strict tools/typescript_libs.py
	$(UV) run --locked python -m tools.typescript_libs --check

browser-architecture-check: browser-runtime-install
	$(UV) run --locked python -m tools.browser_architecture

BROWSER_GRAPH_PROTOCOL := src/archkeel/render/assets/report-graph-vocabulary.ts src/archkeel/render/assets/report-graph-schema.ts
BROWSER_GRAPH_COMPILER := node tools/browser-runtime/node_modules/typescript/bin/tsc --strict --target ES2022 --module none --newLine lf

browser-graph-generate: browser-runtime-install
	$(UV) run --locked python -m tools.browser_graph_protocol
	$(BROWSER_GRAPH_COMPILER) --outFile src/archkeel/render/assets/report-graph-protocol.js $(BROWSER_GRAPH_PROTOCOL)
	cat tools/browser-runtime/protocol-exports.js >> src/archkeel/render/assets/report-graph-protocol.js
	$(BROWSER_GRAPH_COMPILER) --declaration --emitDeclarationOnly --outFile src/archkeel/render/assets/report-graph-protocol.types.d.ts $(BROWSER_GRAPH_PROTOCOL)
	cat tools/browser-runtime/protocol-exports.types.d.ts >> src/archkeel/render/assets/report-graph-protocol.types.d.ts

browser-graph-check: browser-runtime-install
	$(UV) run --locked mypy --strict tools/browser_graph_protocol.py
	$(UV) run --locked python -m tools.browser_graph_protocol --check
	@set -e; browser_graph_stage=$$(mktemp -d); \
		trap 'rm -rf "$$browser_graph_stage"' EXIT; \
		$(BROWSER_GRAPH_COMPILER) --outFile "$$browser_graph_stage/protocol.js" $(BROWSER_GRAPH_PROTOCOL); \
		cat tools/browser-runtime/protocol-exports.js >> "$$browser_graph_stage/protocol.js"; \
		cmp src/archkeel/render/assets/report-graph-protocol.js "$$browser_graph_stage/protocol.js"; \
		$(BROWSER_GRAPH_COMPILER) --declaration --emitDeclarationOnly --outFile "$$browser_graph_stage/protocol.types.d.ts" $(BROWSER_GRAPH_PROTOCOL); \
		cat tools/browser-runtime/protocol-exports.types.d.ts >> "$$browser_graph_stage/protocol.types.d.ts"; \
		cmp src/archkeel/render/assets/report-graph-protocol.types.d.ts "$$browser_graph_stage/protocol.types.d.ts"
	$(BROWSER_GRAPH_COMPILER) --module esnext --moduleResolution node --moduleSuffixes .types, --allowJs --checkJs --noEmit src/archkeel/render/assets/report-graph-scene.js tests/browser_graph_scene_target.ts src/archkeel/render/assets/report-atlas-deviations.js

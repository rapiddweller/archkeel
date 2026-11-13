.DEFAULT_GOAL := check
MAKEFILE_DIR := $(dir $(lastword $(MAKEFILE_LIST)))
include $(MAKEFILE_DIR)tests/pr-test.mk
include $(MAKEFILE_DIR)tools/full.mk
UV ?= uv
DART_EXECUTABLE ?= dart
FLUTTER_EXECUTABLE ?= flutter

.PHONY: demos demo-studio against amendment-refresh gate full-test ci ci-check ci-core-check ci-pr-check ci-pr-static ci-pr-report-check pr-test merge-check pr-report-test ci-typescript ci-artifacts-clean mermaid check test collector-safety python-compat typescript-native typescript-compiler-check dart-test lint typecheck self-validate self-observation demo demo-onboarding demo-dart demo-typescript demo-architecture demo-uml demo-screenshots browser-install report-browser-tests report-pages plugin plugin-release build smoke release-check architecture-graph-schema report-timing flutter-demo-check browser-runtime-install browser-runtime-generate browser-runtime-check typescript-libs-check browser-graph-generate browser-graph-check browser-architecture-check native-check native-corpus self-validate-native native-report native-tools cargo-deny-install native-wheel golden-record dual-run dual-run-record dual-run-collector

# These stages consume the previous stage's success, even with make -j.
.NOTPARALLEL: gate full-test release-check ci ci-check ci-core-check ci-pr-check ci-pr-static ci-pr-report-check

ci: ci-check mermaid

ci-check: ci-artifacts-clean ci-core-check report-timing

ci-pr-check: ci-pr-static pr-test

ci-pr-static: $(if $(strip $(BASE)),against,self-validate) lint typecheck browser-architecture-check

ci-pr-report-check: browser-runtime-check browser-graph-check pr-report-test

pr-test: browser-runtime-install
	$(UV) run --locked python -m pytest -n 4 --dist=loadgroup --max-worker-restart=0 \
		-q --durations=10 --junitxml=test-artifacts/pytest/pr-core.xml $(if $(AREA),--area="$(AREA)",) \
		$(PR_TEST_FILES)

# Checks a pull request before its merge: make merge-check PR=<number> (tools/merge_check.py).
merge-check:
	@test -n "$(PR)" || { echo "PR is required"; exit 2; }
	$(UV) run --locked python -m tools.merge_check "$(PR)"

pr-report-test:
	$(UV) run --locked python -m pytest -n 2 --dist=loadfile --max-worker-restart=0 -q \
		--junitxml=test-artifacts/pytest/pr-report.xml \
		tests/test_graph_scene_protocol.py tests/test_atlas_deviation_boundary.py tests/test_report_renderer_units.py

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

amendment-refresh: BASE ?= origin/main
amendment-refresh:
	$(UV) run --locked python -m tools.against --refresh --base "$(BASE)"

self-validate:
	@mkdir -p test-artifacts/validation
	@$(UV) run --locked archkeel validate --root . --baseline architecture-baseline.json --json > test-artifacts/validation/result.json || { cat test-artifacts/validation/result.json; exit 1; }
	@python3 -c 'import json; d=json.load(open("test-artifacts/validation/result.json")); print("Architecture rules: %s; diagnostics: %s; full result: test-artifacts/validation/result.json" % (d["declared_rules"], len(d["diagnostics"])))'

TEST_WORKERS ?= 2

# Pinned Rust tools of the native checks (AD-316, AD-317).
CARGO_DENY_VERSION := 0.20.2
# SHA-256 of the x86_64-unknown-linux-musl release archive of cargo-deny that CI installs.
CARGO_DENY_SHA256 := 9f12ed4c49936e09b48bf862b595cde2fe64fcbd9d74dfacac6131ca824c8d5f
CARGO_AUDITABLE_VERSION := 0.7.7

# Issue #880: these two tests run the whole dual-run corpus and use about 75 % of the CPU time of
# the native-check tests. CI runs each in a leg of the native-corpus job, parallel to the native
# job, and that job runs native-check with NATIVE_SPLIT=1. Locally, native-check runs all tests.
NATIVE_CORPUS_TESTS := \
	tests/test_native_core.py::test_the_scope_proof_gives_the_verdict_of_python_or_an_exact_name_on_every_case \
	tests/test_native_core.py::test_the_s3_sections_equal_python_on_every_case_whose_reply_the_store_accepts
# pytest reads its options from PYTEST_ADDOPTS, so the test list below stays one line.
native-check: export PYTEST_ADDOPTS = -n 4 --max-worker-restart=0 $(if $(NATIVE_SPLIT),$(addprefix --deselect ,$(NATIVE_CORPUS_TESTS)))

# One leg of the native-corpus job: make native-corpus LEG=<n> runs test n of NATIVE_CORPUS_TESTS.
native-corpus:
	$(UV) run --locked python -m pytest -q $(or $(word $(LEG),$(NATIVE_CORPUS_TESTS)),$(error LEG must be a number from 1 to $(words $(NATIVE_CORPUS_TESTS))))

# Rust code in native/ (AD-316). Run from native/ so that rust-toolchain.toml selects the toolchain.
native-check:
	@cargo deny --version 2>/dev/null | grep -qx "cargo-deny $(CARGO_DENY_VERSION)" || \
		{ echo "native-check needs cargo-deny $(CARGO_DENY_VERSION): run make native-tools"; exit 2; }
	cd native && cargo fmt --all --check
	cd native && cargo clippy --locked --all-targets -- -D warnings
	cd native && cargo clippy --locked --all-targets --features dump -- -D warnings
	cd native && cargo deny --locked check
	cd native && cargo test --locked
	$(UV) run --locked python -m pytest -q tests/test_rust_clones.py tests/test_rust_api.py tests/test_native_contract_rules.py tests/test_native_expected_gaps.py tests/test_rust_source.py tests/test_collector_native_rust_module_oracle.py tests/test_collector_native_rust_definitions_oracle.py tests/test_collector_native_rust_symbols.py tests/test_collector_native_rust_receivers_compiled.py tests/test_rust_contract_parity.py tests/test_native_core.py tests/test_collector_native_dart_discovery.py tests/test_native_report.py tests/test_collector_native_dart_syntax.py tests/test_collector_native_dart_sites.py tests/test_collector_native_dart_definitions.py tests/test_collector_native_dart_sdk.py tests/test_collector_native_dart_declarations.py tests/test_collector_native_dart_collection.py tests/test_rust_contract_tree_parity.py tests/test_rust_contract_against_parity.py tests/test_rust_contract_amendment_parity.py tests/test_rust_contract_baseline_parity.py
	$(UV) run --locked python -m pytest -q -n 0 tests/test_native_self_rules.py tests/test_native_self_contract.py
	$(MAKE) self-validate-native

# AD-335: Archkeel checks the Rust of native/ with its own Rust collector and its own contract.
# The build of this tree is what a platform wheel bundles (AD-350), so the run places it where the
# host looks for the bundled binary and removes it after, and the pure wheel never carries it.
# Like the wheel build, it stamps the installed package version, in a target directory of its own.
self-validate-native:
	cd native && ARCHKEEL_VERSION="$$($(UV) run --locked python -c 'from archkeel.analyzer.runtime import package_version; print(package_version())')" \
		cargo build --locked --bin archkeel-rust-collector --target-dir target/self
	@mkdir -p test-artifacts/validation-native src/archkeel/_native
	@cp native/target/self/debug/archkeel-rust-collector src/archkeel/_native/archkeel-rust-collector
	@$(UV) run --locked archkeel report --config native/archkeel.toml --output test-artifacts/validation-native/architecture.json --json > test-artifacts/validation-native/result.json || true; \
		rm -f src/archkeel/_native/archkeel-rust-collector; rmdir src/archkeel/_native 2>/dev/null || true
	@# AD-357: the result must equal the pinned gaps and rule statuses of native/expected-gaps.json.
	$(UV) run --locked python tools/native_expected.py test-artifacts/validation-native/result.json native/expected-gaps.json
	@echo "Native architecture rules: as pinned in native/expected-gaps.json; full result: test-artifacts/validation-native/result.json"

# AD-343: record the golden replies of the Python collector. REASON says why a reply changes.
# The source must be committed, or set ALLOW_DIRTY=1 to log the commit as +dirty.
golden-record:
	$(UV) run --locked python tests/golden_record.py --language "$(LANGUAGE)" --case "$(CASE)" --reason "$(REASON)" $(if $(ALLOW_DIRTY),--allow-dirty,)

# AD-360: record the oracles of the Python engine again, after a reviewed change of its result.
# REASON says why; the source must be committed (or ALLOW_DIRTY=1).
dual-run-record: dual-run-collector
	$(UV) run --locked python -m tools.dual_run record --reason "$(REASON)" $(if $(ALLOW_DIRTY),--allow-dirty,) $(DUAL_RUN_ARGS)

# AD-327: counts of the lints that only report. They never fail the build.
native-report:
	@$(UV) run --locked python tools/rust_api.py
	@$(UV) run --locked python tools/rust_clones.py --list | head -1
	@for lint in indexing_slicing arithmetic_side_effects cast_possible_truncation; do \
		printf '%s: ' $$lint; \
		(cd native && cargo clippy --locked --message-format short -- -W clippy::$$lint 2>&1) | \
			grep -c '^[^ ]*: warning: ' || true; \
	done

# Build the pinned tools from crates.io with their own Cargo.lock; cargo skips an installed tool.
native-tools:
	cargo install --locked cargo-deny@$(CARGO_DENY_VERSION) cargo-auditable@$(CARGO_AUDITABLE_VERSION)

# CI installs the prebuilt Linux x86_64 cargo-deny: it checks the SHA-256 and builds nothing.
cargo-deny-install:
	@set -eu; name=cargo-deny-$(CARGO_DENY_VERSION)-x86_64-unknown-linux-musl; \
		work=$$(mktemp -d); trap 'rm -rf "$$work"' 0; \
		curl -fsSL -o "$$work/$$name.tar.gz" \
			"https://github.com/EmbarkStudios/cargo-deny/releases/download/$(CARGO_DENY_VERSION)/$$name.tar.gz"; \
		echo "$(CARGO_DENY_SHA256)  $$work/$$name.tar.gz" | sha256sum --check --strict; \
		tar -xzf "$$work/$$name.tar.gz" -C "$$work"; \
		mkdir -p "$${CARGO_HOME:-$$HOME/.cargo}/bin"; \
		install -m 0755 "$$work/$$name/cargo-deny" "$${CARGO_HOME:-$$HOME/.cargo}/bin/cargo-deny"

LINT_PATHS := src tests tools/mermaid_blocks.py \
	tools/report_pages.py tools/package_plugin.py tools/against.py \
	fixtures/reproduce_milestone1.py fixtures/reproduce_onboarding.py \
	fixtures/reproduce_dart.py fixtures/reproduce_snapshot_check.py fixtures/consume_result.py \
	fixtures/reproduce_typescript.py \
	fixtures/architecture_demo.py fixtures/demo_catalog_*.py \
	tools/architecture_graph_schema.py tools/report_timing.py tools/browser_runtime.py tools/browser_graph_protocol.py tools/browser_architecture.py tools/publish_release.py tools/typescript_libs.py tools/ci_budget.py tools/ci_daily.py tools/merge_check.py tools/rust_clones.py tools/rust_api.py tools/rust_source.py tools/native_expected.py tools/dart_grammar_parity.py tools/dart_discovery_parity.py tools/dart_syntax_parity.py tools/dart_unicode_tables.py \
	tools/dart_sdk_parity.py tools/dart_declarations_parity.py tools/dart_collection_parity.py tools/dual_run.py tools/dual_run_corpus.py tools/dual_run_oracle.py tools/dual_run_python.py \
	tools/dual_run_capture.py tools/dual_run_tree.py \
	native/hatch_build.py

# Builds the demo gallery in test-artifacts/pages; Full publishes this same build.
demos:
	rm -rf test-artifacts/pages
	$(UV) run --locked python -m tools.report_pages
	$(MAKE) demo-studio

demo-studio:
	$(UV) run --locked python -m fixtures.demo_catalog_studio

report-pages: report-timing demos
	cp test-artifacts/report-timing/architecture.json test-artifacts/report-timing/architecture.report.html \
		test-artifacts/report-timing/architecture.detail*.html test-artifacts/pages/

architecture-graph-schema:
	$(UV) run --locked python -m tools.architecture_graph_schema schema/architecture-graph.schema.json --contract schema/architecture-contract.schema.json --contract schema/architecture-contract-3.0.schema.json --contract schema/architecture-contract-3.1.schema.json --contract schema/architecture-contract-3.2.schema.json --contract schema/architecture-contract-3.3.schema.json --contract schema/architecture-contract-3.4.schema.json --contract schema/architecture-contract-3.5.schema.json --contract schema/architecture-contract-3.6.schema.json --contract schema/architecture-contract-3.7.schema.json --contract schema/architecture-contract-3.8.schema.json --contract schema/architecture-contract-3.9.schema.json --contract schema/architecture-contract-3.10.schema.json --contract schema/architecture-contract-3.11.schema.json --contract schema/architecture-contract-3.12.schema.json --contract schema/architecture-contract-3.13.schema.json --contract schema/architecture-contract-3.14.schema.json --comparison schema/architecture-comparison.schema.json --report schema/architecture-report.schema.json --source-inventory schema/source-member-inventory.schema.json --source-profile schema/architecture-ir-python-decoded.schema.json --projection schema/architecture-projection.schema.json --command schema/architecture-command-2.0.schema.json --view-spec schema/view-spec.schema.json --view-check schema/view-check.schema.json --story-trace schema/story-trace.schema.json

lint:
	$(UV) run --locked ruff format --check $(LINT_PATHS)
	$(UV) run --locked ruff check $(LINT_PATHS)

# The build hook imports hatchling, which is a build requirement, not a locked dependency.
HATCHLING_VERSION := 1.33.0

typecheck:
	$(UV) run --locked mypy src/archkeel tools/against.py tools/architecture_graph_schema.py tools/report_timing.py tools/browser_architecture.py tools/publish_release.py tools/ci_budget.py tools/ci_daily.py tools/merge_check.py tools/rust_clones.py tools/rust_api.py tools/rust_source.py tools/native_expected.py tools/dart_grammar_parity.py tools/dart_discovery_parity.py tools/dart_syntax_parity.py tools/dart_sdk_parity.py tools/dart_declarations_parity.py tools/dart_collection_parity.py tools/dart_unicode_tables.py tools/dual_run.py
	$(UV) run --locked --with hatchling==$(HATCHLING_VERSION) mypy --strict native/hatch_build.py

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

plugin:
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	$(UV) run --locked python -m tools.package_plugin "$(OUTPUT)"

plugin-release:
	@test -n "$(VERSION)" || { echo "VERSION is required"; exit 2; }
	$(UV) run --locked python -m tools.package_plugin --release-version "$(VERSION)" --expected-version "$(VERSION)" "build/plugin-release/archkeel-plugin-$(VERSION)"
	$(UV) run --locked python -m tools.package_plugin --check --release-version "$(VERSION)" --expected-version "$(VERSION)" "build/plugin-release/archkeel-plugin-$(VERSION).zip"

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

browser-architecture-check: browser-runtime-install
	$(UV) run --locked python -m tools.browser_architecture
	@mkdir -p test-artifacts/validation
	@$(UV) run --locked archkeel validate --root . --config docs/architecture/studio-ui.toml --json > test-artifacts/validation/studio-ui.json || { cat test-artifacts/validation/studio-ui.json; exit 1; }
	@echo "Studio UI architecture: PASS (AD-290)"

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

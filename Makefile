.DEFAULT_GOAL := check
MAKEFILE_DIR := $(dir $(lastword $(MAKEFILE_LIST)))
include $(MAKEFILE_DIR)tests/pr-test.mk
include $(MAKEFILE_DIR)tools/full.mk
UV ?= uv
DART_EXECUTABLE ?= dart
FLUTTER_EXECUTABLE ?= flutter

.PHONY: gate full-test ci ci-check ci-core-check ci-pr-check ci-pr-static ci-pr-report-check pr-test merge-check pr-report-test ci-artifacts-clean mermaid check test typescript-compiler-check lint typecheck flutter-demo-check plugin plugin-release build smoke release-check browser-runtime-install browser-runtime-generate browser-runtime-check typescript-libs-check browser-graph-generate browser-graph-check browser-architecture-check core native-check self-validate self-validate-native self-validate-shell native-report native-tools cargo-deny-install native-wheel golden-record report-gallery

# These stages consume the previous stage's success, even with make -j.
.NOTPARALLEL: gate full-test release-check ci ci-check ci-core-check ci-pr-check ci-pr-static ci-pr-report-check

ci: ci-check mermaid

ci-check: ci-artifacts-clean ci-core-check self-validate-native self-validate-shell

ci-pr-check: ci-pr-static pr-test

ci-pr-static: lint typecheck browser-architecture-check

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
		tests/test_report_renderer_units.py

ci-artifacts-clean:
	rm -rf test-artifacts/validation test-artifacts/validation-native

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

TEST_WORKERS ?= 2

# Pinned Rust tools of the native checks (AD-316, AD-317).
CARGO_DENY_VERSION := 0.20.2
# SHA-256 of the x86_64-unknown-linux-musl release archive of cargo-deny that CI installs.
CARGO_DENY_SHA256 := 9f12ed4c49936e09b48bf862b595cde2fe64fcbd9d74dfacac6131ca824c8d5f
CARGO_AUDITABLE_VERSION := 0.7.7

# pytest reads its options from PYTEST_ADDOPTS, so the test list below stays one line.
native-check: export PYTEST_ADDOPTS = -n 4 --max-worker-restart=0

# Rust code in native/ (AD-316). Run from native/ so that rust-toolchain.toml selects the toolchain.
native-check:
	@cargo deny --version 2>/dev/null | grep -qx "cargo-deny $(CARGO_DENY_VERSION)" || \
		{ echo "native-check needs cargo-deny $(CARGO_DENY_VERSION): run make native-tools"; exit 2; }
	cd native && cargo fmt --all --check
	cd native && cargo clippy --locked --all-targets -- -D warnings
	cd native && cargo clippy --locked --all-targets --features dump -- -D warnings
	cd native && cargo deny --locked check
	cd native && cargo test --locked
	$(UV) run --locked python -m pytest -q tests/test_repository_hygiene.py tests/test_ir_owners.py tests/test_rust_clones.py tests/test_rust_api.py tests/test_rust_source.py tests/test_native_contract_rules.py tests/test_native_expected_gaps.py tests/test_native_report.py tests/test_native_core.py tests/test_cli_core_only.py tests/test_cli_core_only_boundary.py tests/test_cli_core_only_build_output.py tests/test_cli_core_only_exit_table.py tests/test_cli_core_only_review.py tests/test_cli_core_only_scan.py tests/test_cli_native_profile_limits.py tests/test_cli_native_core_scan.py tests/test_cli_native_core_scan_rust.py tests/test_cli_native_core_scan_work.py tests/test_cli_native_core_scan_large.py tests/test_collector_native_rust_module_oracle.py tests/test_collector_native_rust_definitions_oracle.py tests/test_collector_native_rust_receivers_compiled.py
	$(UV) run --locked python -m pytest -q -n 0 tests/test_native_self_rules.py tests/test_native_self_contract.py tests/test_native_self_core_rows.py
	$(MAKE) self-validate-native

# AD-432: the core is the only decision path. `archkeel` finds this release build of the checkout.
core:
	cd native && cargo build --locked --release -p archkeel-core

# AD-335: Archkeel checks the Rust of native/ with its own core and its own contract (AD-432).
# The result must equal the pinned gaps, violations and rule statuses of native/expected-gaps.json
# (AD-357). The pinned result has a FAIL, so the exit code of `archkeel` is not the gate.
self-validate-native: core
	@mkdir -p test-artifacts/validation-native
	@$(UV) run --locked archkeel validate --config native/archkeel.toml --json > test-artifacts/validation-native/result.json || true
	$(UV) run --locked python tools/native_expected.py test-artifacts/validation-native/result.json native/expected-gaps.json
	@echo "Native architecture rules: as pinned in native/expected-gaps.json; full result: test-artifacts/validation-native/result.json"

# AD-478: Archkeel checks the Python shell of src/archkeel with its own core and its own contract.
# The result must equal the pinned rows of docs/architecture/target/shell-expected.json.
self-validate-shell: core
	@mkdir -p test-artifacts/validation-shell
	@$(UV) run --locked archkeel validate --config docs/architecture/shell.toml --json > test-artifacts/validation-shell/result.json || true
	$(UV) run --locked python tools/native_expected.py test-artifacts/validation-shell/result.json docs/architecture/target/shell-expected.json
	@echo "Shell architecture rules: as pinned in docs/architecture/target/shell-expected.json; full result: test-artifacts/validation-shell/result.json"

# AD-478: the shell and native/ with their own contracts.
self-validate: self-validate-native self-validate-shell

# AD-462: one report pair for each run of fixtures/matrix.json, in test-artifacts/gallery. The
# shell decides nothing; the job `publish-gallery` of CI publishes this directory.
report-gallery: core
	rm -rf test-artifacts/gallery
	$(UV) run --locked python -m tools.report_gallery --out test-artifacts/gallery --archkeel "$(UV) run --locked archkeel"

# AD-343: record the golden replies of the TypeScript collector. REASON says why a reply changes.
# The source must be committed, or set ALLOW_DIRTY=1 to log the commit as +dirty.
golden-record:
	cd native && cargo build --locked --release -p archkeel-typescript-collector
	$(UV) run --locked python tests/golden_record.py --language "$(LANGUAGE)" --case "$(CASE)" --reason "$(REASON)" --binary native/target/release/archkeel-typescript-collector $(if $(ALLOW_DIRTY),--allow-dirty,)

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

LINT_PATHS := src tests tools/mermaid_blocks.py tools/package_plugin.py \
	tools/browser_runtime.py tools/publish_release.py tools/typescript_libs.py tools/ci_budget.py tools/ci_daily.py tools/merge_check.py tools/rust_clones.py tools/rust_api.py tools/rust_source.py tools/native_expected.py tools/release_core.py tools/dart_grammar_parity.py tools/dart_unicode_tables.py tools/report_gallery.py \
	native/hatch_build.py

lint:
	$(UV) run --locked ruff format --check $(LINT_PATHS)
	$(UV) run --locked ruff check $(LINT_PATHS)

# The build hook imports hatchling, which is a build requirement, not a locked dependency.
HATCHLING_VERSION := 1.33.0

typecheck:
	$(UV) run --locked mypy src/archkeel tools/publish_release.py tools/ci_budget.py tools/ci_daily.py tools/merge_check.py tools/rust_clones.py tools/rust_api.py tools/rust_source.py tools/native_expected.py tools/release_core.py tools/dart_grammar_parity.py tools/dart_unicode_tables.py tools/report_gallery.py
	$(UV) run --locked --with hatchling==$(HATCHLING_VERSION) mypy --strict native/hatch_build.py

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

# AD-290, AD-432: the browser assets and the Studio UI are TypeScript projects that the core checks.
# The Studio UI result must equal its pinned result (one typed UNKNOWN), so it is not a PASS.
browser-architecture-check: browser-runtime-install core
	@mkdir -p test-artifacts/validation
	@$(UV) run --locked archkeel validate --config docs/architecture/browser.toml --json > test-artifacts/validation/browser.json || true
	$(UV) run --locked python tools/native_expected.py test-artifacts/validation/browser.json docs/architecture/target/browser-expected.json
	@$(UV) run --locked archkeel validate --config docs/architecture/studio-ui.toml --json > test-artifacts/validation/studio-ui.json || true
	$(UV) run --locked python tools/native_expected.py test-artifacts/validation/studio-ui.json docs/architecture/target/studio-ui-expected.json

BROWSER_GRAPH_PROTOCOL := src/archkeel/render/assets/report-graph-vocabulary.ts src/archkeel/render/assets/report-graph-schema.ts
BROWSER_GRAPH_COMPILER := node tools/browser-runtime/node_modules/typescript/bin/tsc --strict --target ES2022 --module none --newLine lf

browser-graph-generate: browser-runtime-install
	$(BROWSER_GRAPH_COMPILER) --outFile src/archkeel/render/assets/report-graph-protocol.js $(BROWSER_GRAPH_PROTOCOL)
	cat tools/browser-runtime/protocol-exports.js >> src/archkeel/render/assets/report-graph-protocol.js
	$(BROWSER_GRAPH_COMPILER) --declaration --emitDeclarationOnly --outFile src/archkeel/render/assets/report-graph-protocol.types.d.ts $(BROWSER_GRAPH_PROTOCOL)
	cat tools/browser-runtime/protocol-exports.types.d.ts >> src/archkeel/render/assets/report-graph-protocol.types.d.ts

browser-graph-check: browser-runtime-install
	@set -e; browser_graph_stage=$$(mktemp -d); \
		trap 'rm -rf "$$browser_graph_stage"' EXIT; \
		$(BROWSER_GRAPH_COMPILER) --outFile "$$browser_graph_stage/protocol.js" $(BROWSER_GRAPH_PROTOCOL); \
		cat tools/browser-runtime/protocol-exports.js >> "$$browser_graph_stage/protocol.js"; \
		cmp src/archkeel/render/assets/report-graph-protocol.js "$$browser_graph_stage/protocol.js"; \
		$(BROWSER_GRAPH_COMPILER) --declaration --emitDeclarationOnly --outFile "$$browser_graph_stage/protocol.types.d.ts" $(BROWSER_GRAPH_PROTOCOL); \
		cat tools/browser-runtime/protocol-exports.types.d.ts >> "$$browser_graph_stage/protocol.types.d.ts"; \
		cmp src/archkeel/render/assets/report-graph-protocol.types.d.ts "$$browser_graph_stage/protocol.types.d.ts"
	$(BROWSER_GRAPH_COMPILER) --module esnext --moduleResolution node --moduleSuffixes .types, --allowJs --checkJs --noEmit src/archkeel/render/assets/report-graph-scene.js tests/browser_graph_scene_target.ts src/archkeel/render/assets/report-atlas-deviations.js

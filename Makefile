.DEFAULT_GOAL := check
MAKEFILE_DIR := $(dir $(lastword $(MAKEFILE_LIST)))
include $(MAKEFILE_DIR)tools/full.mk
UV ?= uv
DART_EXECUTABLE ?= dart
FLUTTER_EXECUTABLE ?= flutter

.PHONY: gate full-test ci ci-check ci-core-check ci-pr-check ci-pr-static decision-index fast-test pr-native-lint pr-gate pr-gate-report pr-precheck pr-selected-test merge-check ci-artifacts-clean mermaid check test typescript-compiler-check lint typecheck flutter-demo-check plugin plugin-release build sdist smoke release-check browser-runtime-install browser-runtime-generate browser-architecture-check typescript-libs-check generated-check core native-check self-validate self-validate-native self-validate-shell self-validate-system native-report native-tools cargo-deny-install native-wheel golden-record report-gallery

# These stages consume the previous stage's success, even with make -j.
.NOTPARALLEL: gate full-test release-check ci ci-check ci-core-check ci-pr-check ci-pr-static pr-gate

ci: ci-check mermaid

ci-check: ci-artifacts-clean ci-core-check self-validate-native self-validate-shell

ci-pr-check: pr-gate

ci-pr-static: lint typecheck

generated-check: browser-runtime-install
	cd native && cargo test --locked -p archkeel-core the_committed_
	cd native && cargo test --locked -p archkeel-facts the_committed_
	cd native && cargo test --locked -p archkeel-report the_light_palette_matches_the_design_tokens
	$(UV) run --locked python tools/rust_api.py --check
	$(UV) run --locked python tools/browser_runtime.py --check

browser-runtime-generate: browser-runtime-install
	$(UV) run --locked python tools/browser_runtime.py

# AD-752: the index of the decision records is generated from the files, not committed.
decision-index:
	@mkdir -p test-artifacts
	$(UV) run --locked python tools/decision_index.py --write test-artifacts/decision-index.md

# AD-674: the fast tests (everything but tests/areas.py SLOW_FILES). The main tier runs one area in each
# job (AREA=...); the PR tier runs the areas that the change selects (make pr-gate). A floor in
# tests/area_floors.json makes an empty or shrunken selection fail.
FAST_TEST = ARCHKEEL_REQUIRE_PREBUILT=1 $(UV) run --locked python -m pytest -n 4 --dist=loadgroup --max-worker-restart=0 \
	-q --durations=10 --junitxml=test-artifacts/pytest/fast.xml

fast-test: core browser-runtime-install
	$(FAST_TEST) --tier fast -m 'not native_wheel and not slow' $(if $(AREA),--area="$(AREA)",)

# AD-674: the PR gate, at most 3 minutes: static checks, the core build, the self and system check,
# and the fast tests of the areas that the change selects (tools/select_areas.py).
PR_BASE ?= origin/main
# SKIP_STATIC=1: the workflow ran `make ci-pr-static` beside the core build (AD-754).
ifneq ($(strip $(KEEP_GOING)),)
# AD-756: KEEP_GOING=1 runs every step and prints all failures at the end (tools/pr_report.py).
pr-gate: pr-gate-report
else
pr-gate: $(if $(strip $(SKIP_STATIC)),,ci-pr-static) self-validate pr-selected-test
endif

# AD-756: the cheap static checks (about 20 s) for an author to run before every push.
pr-precheck:
	$(UV) run --locked python tools/pr_report.py --mode precheck --base "$(PR_BASE)"

# AD-756: every step of the gate, cheap ones first, with one summary of all failures.
pr-gate-report: core browser-runtime-install
	$(UV) run --locked python tools/pr_report.py --mode report --base "$(PR_BASE)"

# AD-756: Rust format and lint in the PR gate when the change touches native/: `cargo fmt --check` for the
# whole workspace (about 2 s), `clippy -D warnings` for the touched crates only (tools/native_touched.py), and
# the clone gate and the API gate of the Rust sources (about 12 s; they sit in the main tier otherwise).
pr-native-lint:
	@crates="$$($(UV) run --locked python tools/native_touched.py "$(PR_BASE)")"; \
	if [ -z "$$crates" ]; then echo "native lint: native/ is unchanged, nothing to check"; exit 0; fi; \
	echo "native lint: fmt and clippy for '$$crates'"; \
	(cd native && cargo fmt --all -- --check) && \
	{ [ "$$crates" = "-" ] || (cd native && cargo clippy --locked --all-targets $$crates -- -D warnings); } && \
	$(UV) run --locked python -m pytest -q -p no:cacheprovider -n 0 tests/test_rust_clones.py tests/test_rust_api.py

pr-selected-test: core browser-runtime-install
	@areas=$$($(UV) run --locked python tools/select_areas.py "$(PR_BASE)") && echo "areas: $$areas" && \
		eval "$(FAST_TEST) --tier pr -m 'not native_wheel and not slow and not debug_build and not heavy' $$areas"

# Checks a pull request before its merge: make merge-check PR=<number> (tools/merge_check.py).
merge-check:
	@test -n "$(PR)" || { echo "PR is required"; exit 2; }
	$(UV) run --locked python -m tools.merge_check "$(PR)"

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

# AD-674: the Python tests of native/ (tests/areas.py) run in the area jobs of the main tier, so native-check
# holds the Rust checks and the self-check only.
# Rust code in native/ (AD-316). Run from native/ so that rust-toolchain.toml selects the toolchain.
native-check:
	@cargo deny --version 2>/dev/null | grep -qx "cargo-deny $(CARGO_DENY_VERSION)" || \
		{ echo "native-check needs cargo-deny $(CARGO_DENY_VERSION): run make native-tools"; exit 2; }
	cd native && cargo fmt --all --check
	cd native && cargo clippy --locked --all-targets -- -D warnings
	cd native && cargo clippy --locked --all-targets --no-default-features -- -D warnings
	cd native && cargo clippy --locked --all-targets --features dump,harness -- -D warnings
	cd native && cargo deny --locked check
	cd native && cargo test --locked
	$(MAKE) self-validate-native

# AD-754: the gate builds the core with a fast profile: no LTO, 16 codegen units, opt-level 1. The verdicts do not depend
# on it; the shipped wheel, the nightly run and a build without ARCHKEEL_CORE_PROFILE keep the release profile.
CORE_PROFILE_ENV := $(if $(filter gate,$(ARCHKEEL_CORE_PROFILE)),CARGO_PROFILE_RELEASE_LTO=false CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16 CARGO_PROFILE_RELEASE_OPT_LEVEL=1,)

# AD-432: the core is the only decision path. `archkeel` finds this release build of the checkout.
# AD-732, AD-736: with ARCHKEEL_CORE_SOURCE=cache (CI restored the core from its cache) and
# ARCHKEEL_NATIVE_TREE (the hash of the native tree) the core is reused only when the stamp next to the
# binary names that tree; else it is built and, with a tree, stamped. A stale binary of main, restored
# from a cache, therefore never stands for the tree of a pull request. CORE_SOURCE is `build` by default.
core:
	@stamp=native/target/release/archkeel-core.tree; tree="$$ARCHKEEL_NATIVE_TREE"; \
	if [ "$$ARCHKEEL_CORE_SOURCE" = cache ] && [ -n "$$tree" ] && [ -x native/target/release/archkeel-core ] && [ "$$(cat $$stamp 2>/dev/null)" = "$$tree" ]; then \
		echo "core: the release core of tree $$tree is used (AD-732)"; \
	else \
		rm -f $$stamp; (cd native && $(CORE_PROFILE_ENV) cargo build --locked --release -p archkeel-core) && \
		{ [ -z "$$tree" ] || echo "$$tree" > $$stamp; }; \
	fi

# AD-672: the pins are ratchets. With origin/main present, growth against it needs a reason in the growth file.
RATCHET_BASE := $(if $(shell git rev-parse --verify -q origin/main),--base-ref origin/main,)

# AD-335: Archkeel checks the Rust of native/ with its own core and its own contract (AD-432).
# Compare the reported rule statuses, gaps and violations with native/expected-gaps.json (AD-357).
self-validate-native: core
	@mkdir -p test-artifacts/validation-native
	@$(UV) run --locked archkeel validate --config native/archkeel.toml --json > test-artifacts/validation-native/result.json || true
	$(UV) run --locked python tools/native_expected.py test-artifacts/validation-native/result.json native/expected-gaps.json --growth native/expected-growth.json $(RATCHET_BASE)
	@echo "Native architecture rules: as pinned in native/expected-gaps.json; full result: test-artifacts/validation-native/result.json"

# AD-478: Archkeel checks the Python shell of src/archkeel with its own core and its own contract.
# The result must equal the pinned rows of docs/architecture/target/shell-expected.json.
self-validate-shell: core
	@mkdir -p test-artifacts/validation-shell
	@$(UV) run --locked archkeel validate --config docs/architecture/shell.toml --json > test-artifacts/validation-shell/result.json || true
	$(UV) run --locked python tools/native_expected.py test-artifacts/validation-shell/result.json docs/architecture/target/shell-expected.json --growth docs/architecture/target/shell-expected-growth.json $(RATCHET_BASE)
	@echo "Shell architecture rules: as pinned in docs/architecture/target/shell-expected.json; full result: test-artifacts/validation-shell/result.json"

# AD-616: ArchKeel as one system: one core run checks each part of the system document and gives one
# status by the status rule of the core, then one line for each part. The pinned result of each part
# is the gate (above), so a FAIL or UNKNOWN (exit 1 or 2) does not stop make; a refusal does.
SYSTEM_DOCUMENT := docs/architecture/architecture-system.json
self-validate-system: core
	@$(UV) run --locked archkeel validate --text --config $(SYSTEM_DOCUMENT); test $$? -le 2

# AD-478: the shell and native/ with their own contracts, then the system line.
self-validate: self-validate-native self-validate-shell self-validate-system

# AD-606: the core checks the Explorer scripts of the report page with their contract. The result is
# shown, not pinned: the gaps of the scripts stay visible until a change removes them.
browser-architecture-check: core browser-runtime-install
	@mkdir -p test-artifacts/validation
	@$(UV) run --locked archkeel validate --config docs/architecture/browser.toml --json > test-artifacts/validation/browser.json || true
	@$(UV) run --locked python -c "import json, collections; f = json.load(open('test-artifacts/validation/browser.json'))['frame']; print('browser:', f['status'], dict(collections.Counter(v[1] for v in f['rules'].values()))); print('gaps:', len(f['collection_gaps'])); [print(f'  {n} {r}') for r, n in collections.Counter(g['reason'].split(':')[0] for g in f['collection_gaps']).most_common()]"

# AD-462: one report pair for each run of fixtures/matrix.json, in test-artifacts/gallery. The
# shell decides nothing; the job `publish-gallery` of CI publishes this directory.
report-gallery: core
	rm -rf test-artifacts/gallery
	$(UV) run --locked python -m tools.report_gallery --out test-artifacts/gallery --source-cache test-artifacts/source-cache --archkeel "$(UV) run --locked archkeel"

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
	tools/publish_release.py tools/typescript_libs.py tools/ci_budget.py tools/ci_daily.py tools/merge_check.py tools/rust_clones.py tools/rust_api.py tools/rust_source.py tools/rust_inert.py tools/pr_report.py tools/native_expected.py tools/release_core.py tools/dart_grammar_parity.py tools/dart_unicode_tables.py tools/report_gallery.py tools/report_gallery_page.py tools/fixture_tree.py tools/fixture_source.py tools/report_product.py tools/report_product_page.py \
	native/hatch_build.py

lint:
	$(UV) run --locked ruff format --check $(LINT_PATHS)
	$(UV) run --locked ruff check $(LINT_PATHS)

# The build hook imports hatchling, which is a build requirement, not a locked dependency.
HATCHLING_VERSION := 1.33.0

typecheck:
	$(UV) run --locked mypy src/archkeel tools/publish_release.py tools/ci_budget.py tools/ci_daily.py tools/merge_check.py tools/rust_clones.py tools/rust_api.py tools/rust_source.py tools/rust_inert.py tools/native_expected.py tools/release_core.py tools/dart_grammar_parity.py tools/dart_unicode_tables.py tools/report_gallery.py
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

# #1313: what a user runs on a checkout. The sdist cannot be installed alone (it has no core), so
# this also builds the platform wheel of this host with the core in `dist/`. It installs
# cargo-auditable when `cargo auditable` is missing; `make native-wheel` adds the full checks.
build: sdist
	@cargo auditable --version >/dev/null 2>&1 || cargo install --locked cargo-auditable@$(CARGO_AUDITABLE_VERSION)
	ARCHKEEL_BUNDLE_NATIVE=1 $(UV) build --wheel --no-sources --out-dir dist
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/*

plugin:
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	$(UV) run --locked python -m tools.package_plugin "$(OUTPUT)"

plugin-release:
	@test -n "$(VERSION)" || { echo "VERSION is required"; exit 2; }
	$(UV) run --locked python -m tools.package_plugin --release-version "$(VERSION)" --expected-version "$(VERSION)" "build/plugin-release/archkeel-plugin-$(VERSION)"
	$(UV) run --locked python -m tools.package_plugin --check --release-version "$(VERSION)" --expected-version "$(VERSION)" "build/plugin-release/archkeel-plugin-$(VERSION).zip"

# The pinned TypeScript compiler: the standard-library catalog check and the compiler check read it.
browser-runtime-install:
	npm ci --prefix tools/browser-runtime --ignore-scripts --no-audit --no-fund

.DEFAULT_GOAL := check
MAKEFILE_DIR := $(dir $(lastword $(MAKEFILE_LIST)))
include $(MAKEFILE_DIR)tools/full.mk
UV ?= uv
DART_EXECUTABLE ?= dart
FLUTTER_EXECUTABLE ?= flutter

# AD-1060: a CI log has no per-crate lines of a successful cargo build. Warnings and errors stay.
# GitHub Actions sets CI.
ifdef CI
export CARGO_TERM_PROGRESS_WHEN := never
export CARGO_TERM_QUIET := true
endif

.PHONY: type-reach-setup gate full-test ci ci-check ci-core-check ci-pr-check ci-pr-static decision-index fast-test pr-native-lint pr-gate pr-gate-report pr-precheck pr-selected-test ci-artifacts-clean check test typescript-compiler-check lint typecheck flutter-demo-check compass-pinned-build plugin plugin-release build sdist smoke release-check browser-runtime-install browser-runtime-generate studio-ui-generate studio-ui-check browser-architecture-check typescript-libs-check core native-check native-test self-validate self-validate-system self-check native-report rustc-facts-e2e rustc-facts-clippy native-tools cargo-deny-install native-wheel report-gallery

# These stages consume the previous stage's success, even with make -j.
.NOTPARALLEL: gate full-test release-check ci ci-check ci-core-check ci-pr-check ci-pr-static pr-gate

ci: ci-check

ci-check: ci-artifacts-clean ci-core-check self-validate

ci-pr-check: pr-gate

ci-pr-static: lint typecheck

browser-runtime-generate: browser-runtime-install
	$(UV) run --locked python tools/browser_runtime.py

studio-ui-generate: browser-runtime-install
	$(UV) run --locked python tools/studio_ui.py

studio-ui-check: browser-runtime-install
	$(UV) run --locked python tools/studio_ui.py --check

# AD-752: the index of the decision records is generated from the files, not committed.
decision-index:
	@mkdir -p test-artifacts
	$(UV) run --locked python tools/decision_index.py --write test-artifacts/decision-index.md

# AD-674: the fast tests (everything but tests/areas.py SLOW_FILES). The main tier runs one area in each
# job (AREA=...); the PR tier runs the areas that the change selects (make pr-gate). An area that
# holds no test after the marker filter fails (AD-1250).
FAST_TEST = ARCHKEEL_REQUIRE_PREBUILT=1 $(UV) run --locked python -m pytest -n 4 --dist=loadgroup --max-worker-restart=0 \
	-q --tb=short -rfEs --durations=10 --junitxml=test-artifacts/pytest/fast.xml

fast-test: core browser-runtime-install
	$(FAST_TEST) -m 'not native_wheel and not slow' $(if $(AREA),--area="$(AREA)",)

# The PR gate runs the main-tier tests of the areas that the change selects.
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
# whole workspace (about 2 s) and `clippy -D warnings` for the touched crates only (tools/native_touched.py).
# PR_HOSTED=1 (the hosted PR gate): the `native` job runs `native-check` (the same fmt, the driver rustfmt and
# the workspace clippy), so this recipe leaves out each of them. A local run keeps all of them.
pr-native-lint:
	@crates="$$($(UV) run --locked python tools/native_touched.py "$(PR_BASE)")"; \
	if [ -z "$$crates" ]; then echo "native lint: native/ is unchanged, nothing to check"; exit 0; fi; \
	echo "native lint: fmt and clippy for '$$crates'"; \
	if [ -z "$(PR_HOSTED)" ]; then \
		(cd native && cargo fmt --all -- --check) && \
		(cd native && rustfmt --edition 2021 --check ../tools/rustc-facts/src/main.rs) || exit $$?; \
	fi; \
	if [ "$$crates" != "-" ] && { [ -z "$(PR_HOSTED)" ] || [ "$$crates" != "--workspace" ]; }; then \
		(cd native && cargo clippy --locked --all-targets $$crates -- -D warnings) || exit $$?; \
	fi

pr-selected-test: core browser-runtime-install
	@if [ -n "$(PR_PARALLEL)" ]; then echo "tests run in parallel jobs"; exit 0; fi; \
	parallel=$$($(UV) run --locked python tools/select_areas.py --job "CLI and core" "$(PR_BASE)") || exit $$?; \
	areas=$$($(UV) run --locked python tools/select_areas.py "$(PR_BASE)") || exit $$?; \
	echo "areas: $$areas"; \
	if [ "$$parallel" = run ]; then \
		native=$$($(UV) run --locked python tools/select_areas.py --job native "$(PR_BASE)") || exit $$?; \
		if [ "$$native" = run ]; then $(MAKE) native-test || exit $$?; fi; \
		eval "$(FAST_TEST) -m 'not native_wheel and not slow' $$areas"; \
	else \
		eval "$(FAST_TEST) -m 'not native_wheel and not slow and not debug_build and not heavy' $$areas"; \
	fi

ci-artifacts-clean:
	rm -rf test-artifacts/validation test-artifacts/validation-system

TEST_WORKERS ?= 2

# Pinned Rust tools of the native checks (AD-316, AD-317).
CARGO_DENY_VERSION := 0.20.2
# SHA-256 of the x86_64-unknown-linux-musl release archive of cargo-deny that CI installs.
CARGO_DENY_SHA256 := 9f12ed4c49936e09b48bf862b595cde2fe64fcbd9d74dfacac6131ca824c8d5f
CARGO_AUDITABLE_VERSION := 0.7.7

# AD-674: the Python tests of native/ (tests/areas.py) run in the area jobs of the main tier, so native-check
# holds the Rust checks only. The self-check of native/ runs in pr-gate, ci-check and make self-validate: with
# compiler facts (AD-1047) its 9 cold `cargo check` runs do not fit into the 15-minute job of native-check.
# Rust code in native/ (AD-316). Run from native/ so that rust-toolchain.toml selects the toolchain.
native-check:
	@cargo deny --version 2>/dev/null | grep -qx "cargo-deny $(CARGO_DENY_VERSION)" || \
		{ echo "native-check needs cargo-deny $(CARGO_DENY_VERSION): run make native-tools"; exit 2; }
	cd native && cargo fmt --all --check
	cd native && rustfmt --edition 2021 --check ../tools/rustc-facts/src/main.rs
	cd native && cargo clippy --locked --all-targets -- -D warnings
	cd native && cargo clippy --locked --all-targets --no-default-features -- -D warnings
	cd native && cargo clippy --locked --all-targets --features dump,harness -- -D warnings
	cd native && cargo deny --locked check
	$(MAKE) native-test

# AD-1047: the compiler type-reach facts (`[scan] rust_type_reach`) need the pinned channel with the
# components of tools/rustc-facts/rust-toolchain.toml: `rustc-dev` for the driver and `llvm-tools`, which
# holds the libLLVM that the driver links (without it the link fails). They add about 160 MB, so only the
# jobs that run the self-check of native/ install them; the wheel jobs do not. Each `rustup toolchain
# install` reads the toolchain file of its directory and adds what the channel lacks. The producer runs
# `cargo check --offline` on the whole workspace of native/, with its dev-dependencies. A cold runner has only
# the crates of the core build, so the check fails; `cargo fetch` is the one online step that prevents it.
type-reach-setup:
	cd native && rustup toolchain install
	cd tools/rustc-facts && rustup toolchain install
	cd native && cargo fetch --locked

# AD-1047: the producer tests that run the real toolchain need the pinned channel with `rustc-dev`. They are
# ignored in `cargo test`; run `make type-reach-setup` first. One thread: the tests share one driver build.
# The collect tests produce the facts and write descriptors; the reader tests of the Rust collector read them.
rustc-facts-e2e:
	rm -rf native/target/e2e-facts && mkdir -p native/target/e2e-facts
	cd native && ARCHKEEL_E2E_OUT=$(CURDIR)/native/target/e2e-facts cargo test --locked -p archkeel-collect --lib -- --ignored --test-threads=1 --nocapture rustc_facts
	cd native && ARCHKEEL_E2E_OUT=$(CURDIR)/native/target/e2e-facts cargo test --locked -p archkeel-rust-collector --lib -- --ignored --test-threads=1 --nocapture type_reach::real_tests

# AD-1047: the driver is outside the workspace, so `native-check` does not lint it. Needs `rustc-dev`.
rustc-facts-clippy:
	cd tools/rustc-facts && RUSTC_BOOTSTRAP=1 cargo clippy --locked -- -D warnings

native-test:
	cd native && cargo build --locked -p archkeel-rust-collector -p archkeel-typescript-collector
	# Cargo puts the core test executable under deps/. Give it the same sibling as the installed core.
	cd native && mkdir -p target/debug/deps && ln -sf ../archkeel-rust-collector ../archkeel-typescript-collector target/debug/deps/
	cd native && cargo test --locked

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
	if [ "$$ARCHKEEL_CORE_SOURCE" = cache ] && [ -n "$$tree" ] && [ -x native/target/release/archkeel-core ] && [ -x native/target/release/archkeel-rust-collector ] && [ -x native/target/release/archkeel-typescript-collector ] && [ "$$(cat $$stamp 2>/dev/null)" = "$$tree" ]; then \
		echo "core: the release core of tree $$tree is used (AD-732)"; \
	else \
		rm -f $$stamp; (cd native && $(CORE_PROFILE_ENV) cargo build --locked --release -p archkeel-core -p archkeel-rust-collector -p archkeel-typescript-collector) && \
		{ [ -z "$$tree" ] || echo "$$tree" > $$stamp; }; \
	fi

# AD-1130: `native/archkeel.toml` asks for compiler type reach, which runs cargo and the build scripts of the
# scanned workspace. Only the operator allows that, by the environment: this is the one place that does it
# for the self-check. `report-gallery` runs the self runs for the report pages.
self-validate-system report-gallery: export ARCHKEEL_ALLOW_BUILD = 1

# AD-616, AD-1380: ArchKeel as one system. One core run checks each part of the system document (the
# shell, the core and the studio) and gives one status by the status rule of the core, then one line for
# each part. The gate (AD-1260) then checks each part on its own rules: it fails when the core gave no
# usable answer, or says FAIL or a violation for any part; UNKNOWN never fails it. A FAIL or UNKNOWN exit
# (1 or 2) of the run does not stop make; a refusal leaves no result, and the gate fails on that.
# AD-1450: when `ARCHKEEL_SELFSCAN_CACHE` names a directory that holds the saved result of main for these exact
# inputs (`tools/self_scan_cache.py`), the scan is not run and the gate judges that result; else the scan runs.
SYSTEM_DOCUMENT := docs/architecture/architecture-system.json
# AD-1088: the JSON of the same run, for `make self-check`.
SYSTEM_RESULT := test-artifacts/validation-system/result.json
self-validate-system: core
	@mkdir -p $(dir $(SYSTEM_RESULT))
	@rm -f $(SYSTEM_RESULT)
	@if [ -n "$(ARCHKEEL_SELFSCAN_CACHE)" ] && $(UV) run --locked python tools/self_scan_cache.py hit --dir "$(ARCHKEEL_SELFSCAN_CACHE)" --out $(SYSTEM_RESULT); then :; \
	else $(UV) run --locked archkeel report --text --topology --config $(SYSTEM_DOCUMENT) --output $(SYSTEM_RESULT) --format json $(if $(NATIVE_SELFCHECK_TIMINGS),--timings "$(NATIVE_SELFCHECK_TIMINGS)"); test $$? -le 2; fi
	@$(UV) run --locked python tools/self_check_gate.py $(SYSTEM_RESULT)
	@echo "Architecture rules of the system: full result: $(SYSTEM_RESULT)"

self-validate: self-validate-system

# AD-1088: the first and the last command of an agent that changes ArchKeel. It runs make self-validate (the
# gates decide the exit code), then prints at most 40 lines from the results of that run: the verdicts, the
# violations, the UNKNOWN causes, and the measured size, import and cycle facts. No checker runs twice.
self-check: core
	@mkdir -p test-artifacts/selfcheck
	@rm -f $(SYSTEM_RESULT)
	@status=0; $(MAKE) -k --no-print-directory self-validate > test-artifacts/selfcheck/self-validate.log 2>&1 || status=$$?; \
	$(UV) run --locked python tools/self_check_summary.py --status $$status --log test-artifacts/selfcheck/self-validate.log; \
	exit $$status

# AD-606: the core checks the Explorer scripts of the report page with their contract. The result is
# shown, not gated: the gaps of the scripts stay visible until a change removes them.
browser-architecture-check: core browser-runtime-install
	@mkdir -p test-artifacts/validation
	@$(UV) run --locked archkeel validate --config docs/architecture/browser.toml --json > test-artifacts/validation/browser.json || test $$? -eq 2
	@$(UV) run --locked python -c "import json, collections; f = json.load(open('test-artifacts/validation/browser.json'))['frame']; print('browser:', f['status'], dict(collections.Counter(v[1] for v in f['rules'].values()))); print('gaps:', len(f['collection_gaps'])); [print(f'  {n} {r}') for r, n in collections.Counter(g['reason'].split(':')[0] for g in f['collection_gaps']).most_common()]"

# AD-462: one report pair for each run of fixtures/matrix.json, in test-artifacts/gallery. The
# shell decides nothing; the job `publish-gallery` of CI publishes this directory.
report-gallery: core
	rm -rf test-artifacts/gallery
	$(UV) run --locked python -m tools.report_gallery --out test-artifacts/gallery --source-cache test-artifacts/source-cache --archkeel "$(UV) run --locked archkeel"

# AD-327: counts of the lints that only report. They never fail the build.
native-report:
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

LINT_PATHS := src tests tools/package_plugin.py \
	tools/publish_release.py tools/typescript_libs.py tools/ci_budget.py tools/ci_daily.py tools/phase_timings.py tools/pr_report.py tools/self_check_gate.py tools/self_check_summary.py tools/file_size.py tools/release_core.py tools/dart_grammar_parity.py tools/dart_unicode_tables.py tools/report_gallery.py tools/report_gallery_page.py tools/report_capabilities.py tools/fixture_tree.py tools/fixture_source.py tools/report_product.py tools/report_product_page.py tools/compass_build.py tools/studio_ui.py \
	native/hatch_build.py

lint:
	$(UV) run --locked ruff format --check $(LINT_PATHS)
	$(UV) run --locked ruff check $(LINT_PATHS)

# The build hook imports hatchling, which is a build requirement, not a locked dependency.
HATCHLING_VERSION := 1.33.0

typecheck:
	$(UV) run --locked mypy src/archkeel tools/publish_release.py tools/ci_budget.py tools/ci_daily.py tools/phase_timings.py tools/self_check_gate.py tools/self_check_summary.py tools/file_size.py tools/release_core.py tools/dart_grammar_parity.py tools/dart_unicode_tables.py tools/report_gallery.py tools/compass_build.py
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

COMPASS_BUILD_OUT ?= test-artifacts/compass-pinned-build

compass-pinned-build:
	$(UV) run --locked python -m tools.compass_build --flutter "$(FLUTTER_EXECUTABLE)" --out "$(COMPASS_BUILD_OUT)"

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

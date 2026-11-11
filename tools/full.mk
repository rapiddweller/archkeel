# The Make recipes that only Full verification runs, and their variables. CI does not run them on a
# pull request. A change here starts Full on a PR; a change in the Makefile does not (AD-280).
# Variables of the Makefile (UV, TEST_WORKERS, the tool versions) are not in this file.

# SKIP_TESTS=1: skip the test suite here; Full verification runs it in area jobs (make full-test).
check: lint typecheck browser-architecture-check $(if $(strip $(SKIP_TESTS)),,test)

gate: $(if $(strip $(BASE)),against,self-validate) release-check

release-check: check build smoke

ci-core-check: PYTEST_STOP := --maxfail=1
ci-core-check: gate typescript-compiler-check browser-graph-check ci-typescript browser-runtime-check typescript-libs-check

# One area of the full suite (tests/areas.py); Full verification runs every area in parallel.
full-test: TEST_WORKERS = 4
full-test: browser-runtime-install test

ci-typescript: OUTPUT := test-artifacts/typescript-demo
ci-typescript: demo-typescript

test:
	$(UV) run --locked $(PYTEST_EXTRA) python -m pytest -n $(TEST_WORKERS) --dist=loadgroup --max-worker-restart=0 \
		-q $(PYTEST_STOP) --durations=20 --junitxml=test-artifacts/pytest/results.xml \
		$(if $(AREA),--area="$(AREA)",)

# Each test that needs Python 3.12 or later, and the files that cover version differences (#724).
python-compat:
	$(UV) run --locked python -m pytest -n $(TEST_WORKERS) --dist=loadfile --max-worker-restart=0 \
		-q --durations=10 --selection=python-compat

# AD-317: build the platform wheel of this host with the binary and its SBOM, check the tag, then
# install the wheel and run the binary. Full verification runs it on each target of the matrix.
NATIVE_TAG ?=
native-wheel:
	cargo install --locked cargo-auditable@$(CARGO_AUDITABLE_VERSION)
	rm -rf dist/native
	ARCHKEEL_BUNDLE_NATIVE=1 $(UV) build --wheel --no-sources --out-dir dist/native
	@test -z "$(NATIVE_TAG)" || ls dist/native/archkeel-*-$(NATIVE_TAG).whl
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/native/*.whl
	ARCHKEEL_NATIVE_WHEEL="$$(ls dist/native/*.whl)" $(UV) run --locked python -m pytest -q \
		-m native_wheel tests/test_collector_native_wheel.py

collector-safety:
	$(UV) run --locked python -m pytest -q tests/test_collection_protocol.py tests/test_typed_collector_protocol.py tests/test_typed_collector_native.py \
		tests/test_collection_process.py tests/test_collection_runtime_gate.py \
		tests/test_runtime.py tests/test_source_trust_boundary.py \
		tests/test_collector_interrupt.py tests/test_windows_launcher_startup.py \
		tests/test_collector_safety_acceptance.py tests/test_collector_liveness_observer.py \
		tests/test_inheritance_proof_transport.py

typescript-compiler-check:
	npx --yes --package typescript@5.9.3 tsc --noEmit --project fixtures/H-uml-typescript/tsconfig.json

# Python implementation architecture is covered by make test, once on Linux in CI.
typescript-native: browser-runtime-install
	$(UV) run --locked python -m pytest -n $(TEST_WORKERS) --dist=loadfile --max-worker-restart=0 \
		-q --durations=10 tests/test_typescript_parse.py \
		tests/test_typescript_inner.py tests/test_typescript_uml_acceptance.py \
		tests/test_typescript_namespace_identities.py \
		tests/test_typescript_collect.py tests/test_typescript_owned_types.py tests/test_typescript_syntax_types.py tests/test_typescript_syntax_compatibility.py tests/test_typescript_source_input.py \
		tests/test_typescript_script_globals.py tests/test_typescript_standard_globals.py tests/test_typescript_umd_providers.py \
		tests/test_browser_architecture.py::test_browser_runner_serializes_windows_config_as_a_posix_port \
		tests/test_typescript_json_fields.py tests/test_typescript_config.py tests/test_typescript_string_constructs.py \
		tests/test_typescript_config_reference.py \
		tests/test_typescript_resolve.py tests/test_typescript_bundler.py tests/test_typescript_provenance.py \
		tests/test_typescript_init_acceptance.py tests/test_typescript_demo.py

dart-test:
	$(UV) run --locked python -m pytest -n $(TEST_WORKERS) --dist=worksteal --max-worker-restart=0 \
		-q --durations=10 tests/test_dart_*.py \
		tests/test_uml_source_facts.py tests/test_language_collectors.py \
		tests/test_flutter_demo.py::test_flutter_variant_reports_keep_pass_fail_unknown_and_coverage_distinct

# The same commit measured 80-96s on hosted runners; allow for runner noise.
REPORT_MAX_SECONDS ?= 190
report-timing:
	$(UV) run --locked python -m tools.report_timing --max-seconds "$(REPORT_MAX_SECONDS)"

demo-typescript:
	@$(UV) run --locked python -m fixtures.reproduce_typescript $(if $(OUTPUT),--output "$(OUTPUT)")

PLAYWRIGHT_VERSION ?= 1.62.0

browser-install:
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m playwright install --with-deps chromium

report-browser-tests: browser-install
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m pytest -m browser -n 2 --dist=loadfile --max-worker-restart=0 -q

# Twine validates PyPI metadata; it is a build-only tool.
build:
	$(UV) build --no-sources --clear
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/*

smoke:
	$(UV) run --isolated --no-project --with dist/*.whl tests/smoke_test.py
	$(UV) run --isolated --no-project --with dist/*.tar.gz tests/smoke_test.py

typescript-libs-check: browser-runtime-install
	$(UV) run --locked mypy --strict tools/typescript_libs.py
	$(UV) run --locked python -m tools.typescript_libs --check

# AD-360: compare the engine with the recorded oracles in tests/dual_run. Narrow a slice with
# DUAL_RUN_ARGS="--sections modules,packages --families direction --engine-command '<command>'".
dual-run: dual-run-collector
	$(UV) run --locked python -m tools.dual_run compare $(DUAL_RUN_ARGS)

# The Rust cases of the corpus run the Rust collector of this workspace.
dual-run-collector:
	cd native && cargo build --locked -q -p archkeel-rust-collector

# The Make recipes that only Full verification runs, and their variables. CI does not run them on a
# pull request. A change here starts Full on a PR; a change in the Makefile does not (AD-280).
# Variables of the Makefile (UV, TEST_WORKERS, the tool versions) are not in this file.

# SKIP_TESTS=1: skip the test suite here; Full verification runs it in area jobs (make full-test).
check: lint typecheck browser-architecture-check $(if $(strip $(SKIP_TESTS)),,test)

gate: release-check

release-check: check build smoke

ci-core-check: PYTEST_STOP := --maxfail=1
ci-core-check: gate typescript-compiler-check browser-graph-check browser-runtime-check typescript-libs-check

# One area of the full suite (tests/areas.py); Full verification runs every area in parallel.
full-test: TEST_WORKERS = 4
full-test: browser-runtime-install test

test:
	$(UV) run --locked $(PYTEST_EXTRA) python -m pytest -n $(TEST_WORKERS) --dist=loadgroup --max-worker-restart=0 \
		-q $(PYTEST_STOP) --durations=20 --junitxml=test-artifacts/pytest/results.xml \
		$(if $(AREA),--area="$(AREA)",)

# AD-317, AD-436: build the platform wheel of this host with the core and its SBOM, check the tag
# and the content, then install the wheel alone and read the verdicts of its core. Full
# verification runs it on each target of the matrix.
NATIVE_TAG ?=
native-wheel:
	cargo install --locked cargo-auditable@$(CARGO_AUDITABLE_VERSION)
	rm -rf dist/native
	ARCHKEEL_BUNDLE_NATIVE=1 $(UV) build --wheel --no-sources --out-dir dist/native
	@test -z "$(NATIVE_TAG)" || ls dist/native/archkeel-*-$(NATIVE_TAG).whl
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/native/*.whl
	ARCHKEEL_NATIVE_WHEEL="$$(ls dist/native/*.whl)" $(UV) run --locked python -m pytest -q \
		-m native_wheel tests/test_collector_native_wheel.py
	ARCHKEEL_NATIVE_WHEEL="$$(ls dist/native/*.whl)" $(UV) run --locked python -m pytest -q \
		tests/test_cli_installed_wheel.py

# The shell is the only Python of the product (AD-432): its tests on the newest claimed Python.
shell-compat:
	$(UV) run --locked python -m pytest -n $(TEST_WORKERS) --dist=loadgroup --max-worker-restart=0 -q \
		tests/test_cli_core_only.py tests/test_cli_core_only_boundary.py tests/test_cli_core_only_exit_table.py \
		tests/test_cli_core_only_review.py tests/test_cli_core_only_scan.py tests/test_skill.py

typescript-compiler-check:
	npx --yes --package typescript@5.9.3 tsc --noEmit --project fixtures/H-uml-typescript/tsconfig.json

# Twine validates PyPI metadata; it is a build-only tool. The sdist is the only distribution
# without a platform: each wheel carries the core and comes from `make native-wheel` (AD-436).
build:
	$(UV) build --sdist --no-sources --clear
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/*

# The installed package with the release core of this checkout: the wheel of this host, then the
# wheel that an installer builds from the sdist with the same prebuilt core (AD-436).
SMOKE_CORE = $(abspath native/target/release/archkeel-core)
smoke: core
	rm -rf build/smoke
	ARCHKEEL_BUNDLE_NATIVE="$(SMOKE_CORE)" $(UV) build --wheel --no-sources --out-dir build/smoke
	$(UV) run --isolated --no-project --with build/smoke/*.whl tests/smoke_test.py
	ARCHKEEL_BUNDLE_NATIVE="$(SMOKE_CORE)" $(UV) run --isolated --no-project \
		--refresh-package archkeel --with dist/*.tar.gz tests/smoke_test.py

typescript-libs-check: browser-runtime-install
	$(UV) run --locked mypy --strict tools/typescript_libs.py
	$(UV) run --locked python -m tools.typescript_libs --check

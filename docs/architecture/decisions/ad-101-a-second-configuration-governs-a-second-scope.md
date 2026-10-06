# AD-101 A second configuration governs a second scope at the same root

`report` and `validate --config <path>` select a root-relative scan configuration,
defaulting to `archkeel.toml`. Product and neighboring test scopes use separate
files, namespaces and contracts, with one scope per run (#143).
Results and Scan complete explanations name `scan_roots`; a green product scan
must not imply coverage of neighboring tests.

## Why a file, not a framework

Shop/test experiments showed `--root tests` broke provenance containment and
namespace discovery (7 runtime mismatches, 5 subject failures); two roots under
namespace shop produced 7 parse errors. Replacing the default file worked, but
`--config` was unsupported. Existing layout, assignment, requirements, placement
and external rules already governed tests; only configuration selection was missing.

## Rejected

Multiple scan tables/namespaces would add ownership/schema machinery. A test root
would need another repository layout. `check --config` needs another digest-bound
lock; this decision does not add multi-scope check. Prose alone cannot name the
scope a reader sees.

## Limits

- Product imports are external to test scans. External scope rules can constrain
  suites to the product package, but product-module forbidden targets are outside
  the test namespace and exit 2 with `reference.namespace`.
- Duplication and result equivalence remain test/oracle behavior, not import facts.
  CI must run each scope; one pass proves nothing about another.
- Reports need a separate `--output`, such as `test-artifacts/tests/architecture.json`;
  config names do not determine artifact paths.
- Placement rules see classes; layout and requirements govern helpers/fixtures.
  Pytest test classes remain classes.
- The additional parser call moved the self unresolved-call budget from 499 to 500.

## Tests

Config, CLI and terminal tests cover selection and scope display. `test-scope-*`
demos run with `archkeel-tests.toml`, pin failure files and prove unchanged product
bytes with or without the test scope.

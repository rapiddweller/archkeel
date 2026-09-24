# AD-101 A second configuration governs a second scope at the same root

`report` and `validate` take `--config <path>`, a scan configuration relative to `--root`; the
default stays `archkeel.toml`. A repository that keeps its tests beside the product, such as
`datamimic_ce/` and `tests_ce/`, checks them with a second file whose `[scan]` names the test
root, the test namespace and the test contract. The product configuration and contract do not
change. Each run is one scope with one namespace, as before (#143).

A report, validate or check result records the `scan_roots` it read, and the "Scan complete"
reason names them: `All source files under shop were read and parsed; no source file beside
them was read.` Before, the terminal and HTML said "All configured source files were read and
parsed" or "All N files parsed", and only `architecture.json` recorded `source.scope`, so a
green product run could be read as covering the tests beside it.

## Why a file, not a framework

Measured on `main` with the shop sample plus a `tests/` tree and a test contract:

| Attempt | Result |
|---|---|
| `validate --root tests` with `tests/archkeel.toml` | exit 2: provenance under `docs/` is outside the root, and no test file contains the `tests` segment below it, so 7 `runtime_mismatch`, 5 `rule_without_subjects` |
| One `archkeel.toml`, `roots = ["shop", "tests"]`, namespace `shop` | exit 2: 7 `parse_error`, one per test file |
| The test file copied over `archkeel.toml` | exit 0 without the product-module rule below; a moved helper and a suite crossing fail at their files |
| `validate --config archkeel-tests.toml` | exit 2, `unrecognized arguments` |

Every rule the test scope needs already exists: `root_layout`, `complete_assignment`,
`complete_requires`, `symbol_placement`, `complete_external_scope` and
`external_dependency_scope`. What was missing was a way to choose a file other than
`archkeel.toml` at the one root both scopes share.

## Rejected

- Several `[scan]` tables, or a namespace list: one ownership graph over two namespaces and a
  schema change, where two runs already give two separate graphs.
- `--root tests`: module names come from the namespace segment below the root, and contract
  paths are relative to it; the test tree would need its own copy of the repository layout.
- `--config` on `check`: the accepted lock binds one configuration digest, and a second scope
  under `check` needs a second lock. That is the multi-scope machinery #143 asks not to build.
- A documentation sentence alone: nothing a reader saw named what the scan read.

## Limits

- The product is outside the test scan, so a test-to-product import is an external dependency.
  `external_dependency_scope` decides which suites import the product's top-level package. A
  `forbidden_dependency` target such as `shop.store.sqlite` is `reference.namespace`, exit 2,
  so a boundary between a suite and one product module cannot be stated.
- Duplicated tests and result equivalence are behaviour, not import facts. They stay in the
  test and oracle gate.
- CI runs each scope. A pass of one says nothing about the other.
- `report`'s default output path does not depend on `--config`, so a test-scope report needs
  its own `--output`, such as `test-artifacts/tests/architecture.json`; the help and docs say
  so. A default derived from the file name was not chosen: it would guess a path per name.
- `symbol_placement` sees classes only: a moved helper function or fixture is caught by the
  layout and `requires` rules, and a pytest `class TestX` counts as a class.
- One more `add_argument` call on the local `_Parser` is one more unresolved call, so
  Archkeel's own `calls_unresolved` budget moves from 499 to 500.

## Tests

`tests/test_config.py`, `tests/test_cli.py` and `tests/test_terminal.py`;
`tests/test_architecture_demo.py` runs the `test-scope-*` rows of `docs/architecture-demo.md`
with `--config archkeel-tests.toml`, checks each failure's file and checks that the product
scan reads the same bytes with or without the test scope.

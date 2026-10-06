# AD-210: The TypeScript frontend ships in the Python package

TypeScript imports are read by a tree-sitter frontend in `archkeel.analyzer.typescript`, not by
the separately installed npm adapter. This supersedes AD-150's choice of a pinned npm collector;
AD-151's require rules still hold. One `pip install` now covers all three languages, and
analysis needs no Node runtime.

## Boundary

The frontend stays a process collector. `python -I -B -m archkeel.analyzer.typescript.entry`
is the default argv, the same shape as Python and Dart, so isolation, timeout and the output
limit of `analyzer/process.py` apply unchanged. It emits `SourceFacts`; Core owns verdicts.
Analysis installs nothing and executes no project code or scripts.

`parse` is the only module that imports tree-sitter or its grammar; the contract confines both.
`config` reads TSConfig and every snapshot input, `resolve` resolves specifiers, `collect` walks
the files and their local closure. The parser versions are bounded in `pyproject.toml` and
hashed into the collector's runtime provenance, so a different grammar is a different analyzer.

## What is not proven stays UNKNOWN

The frontend re-implements a subset of the compiler's module resolution; it is not a type checker.
Whatever it cannot prove is a `collection_gap` with `full_scope` false, never PASS (AD-90):

- The resolver is at least as strict as `tsc`. The module format of each file decides extension
  and directory-index rules; a format that cannot be proven makes the specifier UNKNOWN.
- `extends` through a package, `exports`, `typesVersions`, project references, unknown compiler
  options and symlinks leaving the snapshot are gaps, never a silent default.
- A construct the grammar cannot parse (`import('x').T<G>`, `export type *`) withholds that
  reference and reports a syntax gap for its file.
- `node_modules` is read only from the snapshot. A package found there is an external package;
  a specifier that resolves nowhere is an unresolved-module gap.

## Acceptance

The Node adapter remains in the repository as the reference oracle. `make typescript-differential`
runs both collectors over the scenario catalogs, the demo variants and the shop fixtures and
classifies every difference:

- equivalent: same edges, targets, flags and coverage;
- more_conservative: the frontend claims less. It passes only with a one-line reason in
  `fixtures/typescript-differential-allowlist.json`; a stale entry fails too;
- suspicious: the frontend claims more or something unclassified. It fails unless allow-listed
  with proof;
- defect: a wrong edge or a false claim. It always fails.

Core verdicts are compared as well, and every FAIL that became UNKNOWN is counted per rule.
Removing the adapter and its Node CI follows separately, after this evidence has run in CI.

## Consequences

- Grammar releases can lag TypeScript syntax; such constructs surface as gaps, not wrong edges.
- JSDoc type imports and computed loaders stay unobserved and are reported when present.
- The resolver implements compiler behavior by hand; the differential is what keeps it honest.

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

The old Node collector and its source are removed. Its output, captured from commit
[`4e215679`](https://github.com/rapiddweller/archkeel/tree/4e215679be7ae063ab1de7da189e4565e7851727),
is preserved as `fixtures/typescript-reference.json`. `make typescript-differential` compares
the native frontend with this immutable reference across 576 cases: 504 equivalent, 72
conservative, and 0 defects. The conservative outcomes remain explicitly allow-listed with
reasons; stale entries and unexpected differences fail. The real-world corpus was low-resolution
and remains a limit of this evidence.

## Consequences

- Grammar releases can lag TypeScript syntax; such constructs surface as gaps, not wrong edges.
- JSDoc type imports and computed loaders stay unobserved and are reported when present.
- The resolver is not a full compiler. Package `extends`, `exports`, `typesVersions`, project
  references and unsupported syntax remain UNKNOWN.
- The frozen differential does not replace a live compiler or broaden these limits.

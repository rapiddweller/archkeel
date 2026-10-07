# AD-210: The TypeScript frontend ships in the Python package

TypeScript source facts are read by a tree-sitter frontend in `archkeel.analyzer.typescript`, not by
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

The `inner-uml-v1` capability adds lexical declarations, signatures, class members and static
relationship sites to the existing SourceFacts records (#348). Core accepts the registered
section set and retains old import-only payloads. Class member inventories certify only their
named lexical kinds; file coverage does not prove a missing declaration. Unresolved sites keep
their source evidence and reasons. The shared graph, Target comparison and renderer remain
the only UML model; publishing these facts does not enable Python-only rule proofs.

## What is not proven stays UNKNOWN

The frontend re-implements a subset of the compiler's module resolution; it is not a type checker.
Unproven import resolution is a `collection_gap` with `full_scope` false (AD-90):

- The resolver is at least as strict as `tsc`. The module format of each file decides extension
  and directory-index rules; a format that cannot be proven makes the specifier UNKNOWN.
- `extends` through a package, `exports`, `typesVersions`, project references, unknown compiler
  options and symlinks leaving the snapshot are gaps, never a silent default.
- A construct the grammar cannot parse (`import('x').T<G>`, `export type *`) withholds that
  reference and reports a syntax gap for its file.
- `node_modules` is read only from the snapshot. A package found there is an external package;
  a specifier that resolves nowhere is an unresolved-module gap.

Inner UML has separate coverage: unresolved calls and partial member inventories keep their
own UNKNOWN assessments without invalidating complete import evidence.

## Acceptance

The old Node collector and its source are removed. Its output, captured from commit
[`4e215679`](https://github.com/rapiddweller/archkeel/tree/4e215679be7ae063ab1de7da189e4565e7851727),
is preserved as `fixtures/typescript-reference.json`. `make typescript-differential` compares
the native frontend across 576 cases: 503 equivalent, 73 conservative and 0 defects in that
corpus. Explained conservative outcomes are allow-listed; stale or unexpected differences fail.
This is not compiler parity; the real-world corpus remains limited by low resolution.

`typescript-reference-demos.json` preserves the two demo fixtures and their 34 original overlays.
Their input hashes still match the frozen reference; adding UML intent to the live demo does
not rewrite the oracle or replace the import-regression corpus.

The 25-case `fixtures/typescript-config-reference.json` checks TypeScript 5.9.3 output-directory
inheritance, selection, `checkJs` and malformed settings without Node during native tests.
Recapture: `node fixtures/capture_typescript_config_reference.cjs /path/to/typescript/lib/typescript.js`.

## Consequences

Alex accepted 715 unresolved self-calls on 2026-10-07 after a bounded sample (`sorted()` fixed
12 of 727). Main had 668; the earlier PR had 662. Other budgets stay unchanged. The scan covers
only `src/archkeel`, including the Python TypeScript frontend. Dynamic callbacks, external
receivers and unpropagated function returns remain uncertain.

- Grammar releases can lag TypeScript syntax; such constructs surface as gaps, not wrong edges.
- JSDoc type imports and computed loaders stay unobserved and are reported when present.
- The frozen differential does not replace a live compiler or broaden these limits.

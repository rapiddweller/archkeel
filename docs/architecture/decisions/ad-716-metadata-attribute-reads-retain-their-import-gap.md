# AD-716: Metadata attribute reads retain their import gap

## Status

Accepted for the Python import survey. This extends AD-574.

## Decision

A direct load of `version`, `distribution`, `distributions` or `PackageNotFoundError` from a
uniquely bound `importlib.metadata` import does not add a second dynamic-import gap. This covers
`import importlib.metadata` followed by `importlib.metadata.version`. The import itself keeps
its non-declarable every-module gap. Stores, deeper chains, rebinding, a star import and a
plain `import importlib` do not use this rule.

## Reason

The import gap covers uncertainty about the imported module, its mutation and code run by its
attributes. A Python 3.12 plant shows that even standard `metadata.version` can lazily import
other modules. A replacement or custom distribution finder can import arbitrary modules. This
rule therefore does not claim that the call is inert or remove the import gap.

## Checks

`hazards_inert_tests.rs` covers both import spellings and aliases, the retained import gap,
stores, rebinding, star imports and deeper chains. Python 3.12 plants check the standard lazy
imports, a replacement and a custom finder that import a module.

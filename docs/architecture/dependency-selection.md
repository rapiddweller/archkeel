# Shared dependency selection

The `contract` component of `native/` owns the selector vocabulary of the dependency rules and
the grammar of their wire form. `Selector`, `SelectorMatch` (`prefix` or `exact`) and `TargetKind`
(`module` or `import_namespace`) are types in `native/contract/src/model.rs`. The grammar is
`native/contract/src/dependency.rs`: it converts the declaration records of
`forbidden_dependency`, `allowed_dependency` and `external_dependency_scope` into those types and
rejects an unknown word or a wrong field type.

Module names, package prefixes, symbols and component identities stay string data. The
`eval` component of `native/` evaluates the rules and produces the receipts; the `report`
component copies the findings. A report does not decide a different interpretation of a dependency
rule. The wire grammar, the default serialization and the version gates are the ones of
[the rule catalog](../rules.md).

# AD-28 An undeclared external dependency is a hole, not a detail

`complete_external_scope` requires every import outside scanned modules and the
stdlib to be covered by `external_dependency_scope`; otherwise it reports a
violation naming the importer. The existing scope rule only constrained named
dependencies, letting undeclared `helpers` or nonexistent packages pass.

`sys.stdlib_module_names` supplies the stdlib set. Python version already binds
comparability ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md));
a version change can change membership. Requiring roughly two hundred stdlib
rules would record no useful architect decision.
Check: an invented-package import fails; the shop's declared externals pass.

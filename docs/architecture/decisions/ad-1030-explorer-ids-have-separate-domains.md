# AD-1030 Explorer IDs have separate domains

**Decision.** Use separate ID domains for components, modules, definitions, and each
relation section in the Explorer snapshot. Use the same element IDs in containment,
relation endpoints, call candidates, and query results. Preserve names for display.

**Reason.** A component and a module can both have the name `app`. A shared key can
prevent the snapshot from publishing or connect a relation to the wrong element.
An external import must also stay separate from a local module with the same name.

**Alternatives.** Skipping duplicate rows removes valid elements. Renaming a component
changes the contract to solve a local projection problem.

**Limit.** IDs apply to the snapshot that returned them. Format 5 publishes the new
IDs. Formats 3 and 4 remain readable with their original IDs.

The fingerprint lists files from the selected project directory. The story
exclusion is relative to that directory, including projects inside a Git work tree.
A repository-root exclusion could omit the tracked files of a nested project.

**Tests.** `tests/test_explorer_queries.py` checks shared names, containment and
relation lookups. `tests/test_explorer_store.py` checks that older formats stay readable.
`tests/test_cli_explorer.py` checks changes inside and outside a nested project.

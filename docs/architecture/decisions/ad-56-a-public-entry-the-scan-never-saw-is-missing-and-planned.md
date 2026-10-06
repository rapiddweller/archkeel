# AD-56 A public entry the scan never saw is missing, and planned exempts target work

Split unused `public` entries by scanned module existence: absent modules yield
`interface.missing`; scanned but unused modules retain `interface.unused`.
A symbol entry is judged by its module, since symbol records omit constants and
`TypeAlias` declarations. Used entries receive neither diagnostic.

Optional `planned` uses the same entry syntax for target work. Unbuilt entries
produce no finding. Built but unreached entries remain planned; an import or
facade signature reaching them produces `interface.planned_built`, requiring
promotion to `public` (AD-79). Reuse public ownership, underscore and namespace
checks. No public list is required alongside it.

Keep an entry in one list. Turning public strings into objects would break old
contracts; duplicating entries in a `planned_public` list would require another
consistency rule. These validation judgments reuse modules and imports, so planned
entries are not projected and the analyzer version stays unchanged.

Issue #10 required distinguishing an unbuilt target facade from a typo; both had
looked merely unused. Limits: a missing symbol in an existing module still reads
unused. Planned entries did not participate in the original inside public match.
Disjointness was intended but not enforced: an entry in both lists could still
produce a public missing diagnostic while planned stayed silent.

Checks: validation tests cover missing, unused, unbuilt, built-unreached and
reached planned entries plus ownership/namespace/underscore constraints. Contract
corpus and demo rows cover planned syntax and lifecycle; self validation carried
no planned entries.

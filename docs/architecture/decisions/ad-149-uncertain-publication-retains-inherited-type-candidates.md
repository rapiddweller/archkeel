# AD-149 Uncertain publication retains inherited type candidates

An uncertain facade route may expose a concrete inherited result type. Discarding that
candidate made root validation call the type unused while an inside contract retained UNKNOWN
(#286).

Record candidate types for every matching publisher, including uncertain routes, at root and
inside scopes. Positive `facade_types` still require proven publication and inheritance.
Validation selects publishers from owned scanned modules, including modules that only re-export.
A candidate produces `interface.usage_unknown`; it grants no publication permission.

Full `validate` controls cover proven and uncertain re-exports, direct inside publication and
an unrelated generic argument. Existing inheritance, ownership and mutation controls remain.
Analyzer version becomes `0.66.1`; wire formats and CE declarations stay unchanged.

# AD-80 `string_literal_compare` follows proven local string constants

`string_literal_compare` keeps its construct name and forms. A comparison is also a finding when
a module-level or class-level name is bound exactly once to a `str` literal. `Final` is an
annotation, not a second mode. Enum members stay out: they are the typed vocabulary this rule is
meant to replace.

Imported, dynamic, conditional, reassigned and named-collection values remain unknown. The
collector does not follow imports or runtime data flow. It fails closed instead of guessing.

Reason: replacing `value == "x"` with `EMPTY: Final = "x"` must not hide the same vocabulary.

Rejected: a second construct or configuration switch; this is stronger evidence for the same
construct. Rejected: import or runtime resolution; that would turn a syntax collector into a
second resolver.

`ANALYZER_VERSION` rises to `0.33.0`; the architecture contract schema is unchanged. Check:
`tests/test_analyzer.py`, `tests/test_architecture_demo.py`, and the generated self-observation.

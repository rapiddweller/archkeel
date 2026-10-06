# AD-80 `string_literal_compare` follows proven local string constants

`string_literal_compare` also matches module/class names bound exactly once to
string literals. `Final` is only an annotation. Exclude enum members: they are
the intended typed vocabulary.

Imported, dynamic, conditional, reassigned and named-collection values remain
unknown. Do not add import/runtime resolution, another construct or a switch.
Replacing `value == "x"` with `EMPTY: Final = "x"` must not hide the vocabulary.

Analyzer version rises to 0.33.0; contract schema stays unchanged.
Checks: analyzer and demo tests, plus generated self-observation.

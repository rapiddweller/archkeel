# AD-1010 A complete Dart interpolated literal has String type

**Status.** Proposed. Extends AD-998.

**Decision.** The linked collector can prove the static type of a `static const` field
whose complete initializer is a string literal. Interpolation and dollar signs inside
raw or escaped strings do not change that type. The target spelling must still bind to
the built-in `String`.

**Reason.** The Dart specification assigns the static type `String` to every string literal,
including literals with interpolation. The parser already distinguishes the whole literal
from an expression that starts with one.
[Dart language specification, strings and interpolation](https://spec.dart.dev/DartLangSpecDraft.pdf)

**Limits.** AD-998's scope and binding checks still apply. A comparison, selector or another
expression gives no literal-type proof. The collector does not evaluate the interpolation.
The linked proof has no wire representation.

**Rejected.** Infer from the written prefix. A comparison can start with the same literal
and have type `bool`.

**Checks.** The CLI checks interpolation, raw and escaped dollar signs, mismatch, a shadowed
type name, a comparison, and a selector. Four route fields in the unchanged Compass target
gain evidence.

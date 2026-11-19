# AD-998 UML compares a proven Dart literal type separately

**Status.** Proposed. Part of #1762. Extends AD-512.

**Reason.** An unannotated `static const` field can have a known Dart type. Recording that type as
a written annotation would misstate the source.

**Decision.** The linked Dart collector records separate type evidence on the existing attribute
fact. A complete plain string literal proves `dart:core` `String`. The same proof records which
of `String` and `int` bind to `dart:core` in the field's scope. The UML comparison first reads
the written annotation. If none exists, it compares the inferred identity with the proven
identity of the target name. A target name with no proven binding stays UNKNOWN.

**Limits.** The first proof reads only a `static const` field without an annotation. The library
must have no imports, exports or parts. The class must have no type parameters or explicit bases.
A declaration that hides a builtin name blocks its use. Interpolation and other expressions
stay UNKNOWN. The in-process receipt does not change the published wire schema.
The parser reads the binding name of a legacy typedef and a named mixin application.
If a declaration has no proven name, the proof stops for that library.

**Rejected.** Store the inferred type as written syntax, or infer from a leading quote. A
boolean comparison can start with a string literal.

**Checks.** `test_cli_native_dart_uml_literal_types.py` checks matches, mismatches, and open
bindings and expressions. The collector test checks the receipt and its absence from the wire.
The unchanged Compass target has 18 undecided assessments, down from 24. The six requires rules
still pass.

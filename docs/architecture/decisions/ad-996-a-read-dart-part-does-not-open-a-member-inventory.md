# AD-996 A read Dart part does not open a member inventory

**Status.** Proposed. Part of #1762. Amends AD-796.

**Reason.** The Dart collector marked every member inventory of a library with a part as partial.
In Compass, that kept 11 closed UML scopes of generated mixins undecided.

**Decision.** A plain `part` adds declarations to a library, not members to a declaration.
Keep the member inventory partial unless each declared part has one proven owner and a complete
parse. The survey proves ownership. The full parse can still stop on its work limit.
The collector does not follow nested part declarations, so such a part cannot complete the proof.
A mixin application or a project extension on the type still makes the inventory partial.

**Rejected.** Ignore `part` directives: an unread part can hide a declaration or extension.
Special-case Freezed names: the proof depends on syntax and ownership, not a code generator.

**Result.** On the unchanged Compass scan, the UML rule has 24 undecided assessments, down from 35.
These concern undrawn `static` modifiers, unrecorded annotations, and unresolved calls.
The six requires rules still pass. The report has no collector gaps and its compiler premise is unchanged.

**Checks.** `H-uml-dart-part-members` passes. Its planted method fails with part-file evidence.
`test_cli_native_dart_uml_parts.py` checks the witness and keeps an unread second part UNKNOWN.
The Dart collector tests retain partial inventories for an extension, a mixin application, and
an unread augmentation.

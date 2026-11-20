# AD-996 A read Dart part does not open a member inventory

**Status.** Proposed. Part of #1762. Amends AD-796.

**Reason.** The Dart collector marked every member inventory of a library with a part as partial.
In Compass, that kept 11 closed UML scopes of generated mixins undecided.

**Decision.** A plain `part` adds declarations to a library, not members to a declaration.
Keep the member inventory partial unless each declared part has one proven owner and a complete
parse. The survey proves ownership. The full parse can still stop on its work limit.
The collector does not follow nested part declarations, so such a part cannot complete the proof.
A mixin application or a project extension on the type still makes the inventory partial.
The survey matches a named `part of` only against a declared library name, and a URI only against
its resolved file. An ownership gap cites the `part of` and each claiming `part` directive.
Only a direct `on` type declared in the same library identifies one extension receiver.
An alias, import, type parameter or other unproven receiver keeps the inventories partial.
When an extension exists, a class with an explicit base stays partial: the base can be the receiver type.

**Rejected.** Ignore `part` directives: an unread part can hide a declaration or extension.
Special-case Freezed names: the proof depends on syntax and ownership, not a code generator.

**Result.** On the unchanged Compass scan, the UML rule has 24 undecided assessments, down from 35.
These concern undrawn `static` modifiers, unrecorded annotations, and unresolved calls.
The six requires rules still pass. The report has no collector gaps and its compiler premise is unchanged.

**Checks.** `H-uml-dart-part-members` passes. Its planted method fails with part-file evidence.
`test_cli_native_dart_uml_parts.py` checks the witness and keeps missing and unselected parts
UNKNOWN. It also checks an extension on a valid typedef and the evidence of wrong owners.
The Dart collector tests retain partial inventories for an extension, a mixin application, and
an unread augmentation.

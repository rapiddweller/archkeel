# AD-748 A Python annotation declares a UML attribute

**Status.** Accepted. Part of #880. This amends AD-518 rule 3.

**Reason.** A UML attribute states a structural declaration. It does not assert that a
runtime object has a value for that attribute. PEP 526 permits a class-body annotation
to declare an instance attribute without a value.

**Decision.** A sole bare class-body annotation can satisfy a UML attribute. It does not
bind a runtime value. The collector admits unshadowed builtin annotations first. It keeps
the other AD-518 class and member gates. A missing or unreadable annotation cannot prove
a requested type. An unproved name is not a declaration.
Absence is not provable for a partial Python inventory, so a missing attribute stays UNKNOWN.

`ClassVar` and other annotations that the collector cannot resolve stay UNKNOWN. This
includes a target that marks the attribute static. A later proof can decide their class
or instance status. The existing runtime binding and call resolution rules keep their
AD-518 semantics. No runtime attribute rule consumes the UML attribute declaration.

**Alternative.** Require a runtime binding. This gives UNKNOWN for a valid structural
declaration and does not express the UML target.

**Checks.** `tests/test_cli_python_symbols.py` checks the amended plants and keeps
unreadable types UNKNOWN. The H-uml fixture checks the complete target.

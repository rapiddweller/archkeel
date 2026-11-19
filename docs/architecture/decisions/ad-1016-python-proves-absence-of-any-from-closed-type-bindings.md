# AD-1016 Python proves absence of Any from closed type bindings

**Status.** Proposed.

**Decision.** The linked Python survey can prove the absence of an `any_annotation`. Read
each parameter, return and annotated assignment. A type position must have a known builtin,
a supported class, or a type expression made from those bindings. Read the modeled builtin
containers. Check local class bindings through sole
imports, including a direct import under a proven `TYPE_CHECKING` guard with deferred
annotations. Follow re-exports to the class that they name.

The proof admits the standard `pathlib.Path` and the class forms that the standard
`dataclass`, `Protocol`, `TypedDict` and `StrEnum` create. The scan must see no writes that
can change the bindings it reads. The rule states the existing
`standard_library_unchanged` premise when it uses this receipt. The collector wire reply
continues to state partial support. Only the trusted linked collector can give this receipt.

**Reason.** AD-880 proves a reported `typing.Any`. It previously left every absence UNKNOWN,
including an inventory of known concrete types. A local binding can name a string or an alias,
so the spelling of a type is insufficient evidence.

**Limits.** An unresolved name, imported value, custom class builder, type alias, quoted
annotation, type comment or type parameter leaves the receipt incomplete. Names that may
read an implicit or mangled class binding also keep the receipt incomplete. A direct observed
`typing.Any` still fails the rule. The proof uses a finite import walk and withholds a receipt
for an escaped module, an unread input or a repository write that can replace a binding.

**Rejected.** Treat an annotation without the token `Any` as safe. Imports, aliases and named
or computed values can hide it. Do not claim full support in a wire reply with no premise receipt.

**Checks.** `tests/test_cli_python_any_identity.py` checks the F-shop proof with and without
its premise. It also plants nested aliases, strings, dynamic forms and a standard-library write.

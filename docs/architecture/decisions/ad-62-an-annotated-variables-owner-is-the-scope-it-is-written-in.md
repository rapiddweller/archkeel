# AD-62 An annotated variable's owner is the scope it is written in, not its bare name

Typing-signal owners include their enclosing module, class and function scopes.
Module variables use `<module>.<name>`; class and local variables include the
class/function chain. Nested function and method annotations use the same recursive
walk, replacing scope-blind `ast.walk`.

Previously `AnnAssign` used a bare target name, so source-scoped `any_annotation`
rules never matched module/class variables. Three probes found only the parameter
violation, missing two variables. Nested methods also lost enclosing class names.

Non-name targets append literal source text to the write scope: `self.x`, `a.b`
or `a[0]`. Do not infer `self`'s class or build a second node-id/scope table.
Nearby call, context, import and symbol collectors already read properly bounded
scopes and needed no change.

Correct ownership exposed
`archkeel.ir.widening._DataclassInstance.__dataclass_fields__`, outside the existing
`Any` allowances. This runtime stand-in for stub-only `_typeshed.DataclassInstance`
needs structurally heterogeneous fields. Exempt exactly that owner with a rationale
(AD-49), not the whole module. Analyzer version rises to 0.26.0 (AD-3).

Limits: the same attribute annotated in two methods has two owners. A class prefix
can cover both; an exact entry covers only one. Owners scope write sites and do
not resolve attribute receivers.
Checks: analyzer probes cover module/class/local variables, parameters, methods
and closures. The any-annotation demo adds a variable alongside a parameter.
Self validation passed with the one exact exemption.

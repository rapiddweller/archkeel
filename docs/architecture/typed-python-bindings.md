# Python binding control API

The Python Source component owns `binding_types.py`. Import collection produces
`AliasBinding.kind: ImportKind`; compiler lexical lookup returns
`NameBinding.kind: BindingKind`. The two vocabularies have different responsibilities:
a module/symbol import is explicitly translated into the richer lexical category.
Unknown, local, unbound, declaration and mixed bindings retain their existing meaning.

The compiler's external module/function/class scope label is decoded into
`CompilerScopeKind` at the existing lookup boundary. An unknown external label
returns no known kind and cannot authorize a module fallback. Nominal AST
`isinstance` checks, unique-binding requirements, declaration ownership,
shadowing, member escape and GenericAlias proof limits are unchanged.

These internal kinds use Enum rather than string-compatible values. The binding
model owns their definitions; module/target names remain string data.
The existing source.AliasBinding and scopes.BindingKind import ports remain
explicit re-exports. Human call-resolution reasons render a kind's value only at
the output boundary; control branches use enum identity or typed membership.

The root contract declares this model as an enum owner and guards its complete
module with `PYTHON-BINDINGS-TYPED-CONTROL`. The inner Python contract declares
the Source port, nominal enum classifiers and the two kind-field annotations.
Native source mutations verify both raw dispatch rejection and kind-to-str
widening against an unchanged Target.

The first increment does not certify every Python parser or resolver module.
Property operations/origins, receiver origins, annotation/calltarget grammar,
wildcard imports and collector bootstrap markers still need their own increments.
The six existing binding control functions are checked through real native
observations of their complete current source files; those focused observations
do not claim a whole-module PASS for the remaining grammar.

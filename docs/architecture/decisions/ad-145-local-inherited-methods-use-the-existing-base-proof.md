# AD-145 Local inherited methods use the existing base proof

A published class with any custom base previously retained an `inherited_surface`
placeholder, even when every local method was visible (#266). Generic method findings
could coexist with that placeholder; ordinary inherited signatures were never checked.

Use the existing public-field base/alias resolution and TypeVar substitution to walk one
proven local chain. Evaluate effective methods in their defining module. Subclass bindings
shadow base members; annotation-only names do not. Constructors, receivers, overloads,
special methods and private-helper exclusions share the direct method policy.

An unproven ancestor withholds inherited signature findings too; class creation may replace them.
A complete surface removes only its synthetic placeholder. Missing or unresolved annotations
still produce actual UNKNOWN positions. Inherited findings retain raw annotations and stable
IDs, and cite both the facade class and defining method. Publication, violations and population
counts consume the same signature proof. Generic uncertain-use candidates remain separate.

## Proof and limits

Class and alias identity reuse `source_binding_unique`; member closure uses the separate
`source_member_binding_static` fact and existing creation/signature proofs.
Visible mutations, executable values, exposed owners and unproven hooks retain UNKNOWN through
aliases and incoming imports, including contained type references and native function namespaces.
Inert native type references remain supported, with unchanged framework exclusions.
Passing a native owner invalidates its provider's shared creation proof; invocation alone does not.
A stable direct stdlib dataclass decorator with literal options, inert creation inputs and unexposed
native providers avoids provider exposure only; generated/inherited surfaces still require proof.
Field-only deferred TypedDict creation shares that owner guard. Unproven creation or bases retain
the exposed class's defining namespace, including generated methods without source declarations.
Incoming mutation revokes the guard. This infers no execution, callback effects or multiple-base order.
Unproven installed class values can receive the owner; an exposed owner's unproven generated namespace saturates the existing finite escape closure.

Sorted base records cannot prove multiple-base precedence. Multiple inheritance, cycles,
unresolved bases or arguments, rebinding, dynamic class bodies and unproven decorators remain
UNKNOWN. This does not execute Python or prove every
CE inheritance surface.

Stable, unshadowed imports of `abc.abstractmethod`, including from-import aliases, preserve
visible method signatures (#288). It adds no descriptor, so one proven `staticmethod` or
`classmethod` can still define the receiver. Custom, called, rebound or shadowed decorators
remain unproven. Module-member escape routes retain their existing UNKNOWN bound.

Standard property creation and getter/setter replacement carry ordered source-binding
proof (#290). Core selects the effective accessors through the same proven base chain,
then checks their signatures in their defining scopes. A copied getter retains its setter;
a fresh property replaces it. Missing proof, custom descriptors and mutations stay UNKNOWN.
An explicit final undecorated binding retains its direct signature findings despite earlier
repeated names. This does not certify an otherwise uncertain class surface.
Module-binding and ordered property proofs require a uniquely bound, stable module-level class;
a same-named nested or replaced class cannot borrow them.

## Alternatives

Dropping every placeholder would hide inherited broad/private signatures. A second resolver or
full MRO engine would duplicate existing type knowledge and exceed the evidence in the records.

## Verification

`tests/test_local_inherited_methods.py` covers inheritance proof and CLI/report/count agreement.
Generic, publication and public-field tests remain controls. Local declared, broad-return and
unresolved-ancestor demos show the three outcomes. `tests/test_boundary_types_abstract_methods.py`
checks full validation, provenance, canonical evidence, overrides, violations and UNKNOWN.

Analyzer version becomes `0.66.0`; the import schema admits optional member-proof and candidate fields.
Contract and IR format versions stay unchanged. CE improvement must
be measured on its unchanged pinned source with this exact analyzer, not inferred from tests.

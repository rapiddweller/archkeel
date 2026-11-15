# AD-543 A written local type proves a Rust receiver

**Status.** Proposed. Part of #880. This extends AD-524.

An initialized top-level `let x: T = ...` or `let mut x: T = ...` gives `x` the written type
after the statement. The receiver proof uses that type with the checks of AD-524. The binding must
be a plain identifier and the type must be a plain path, a shared reference or a unique reference.
The name must have one binding in the function. Generic types, aliases, a `Deref` impl, a macro
that may bind the name, a gate and a mismatched receiver form keep the gap.

The scan reads only locals that are direct statements of the function body. A call before the
semicolon, including one inside the initializer, has no local proof. A nested block, a pattern,
a local without an initializer and a type name that a body binding can hide keep the gap.
These limits avoid assuming a local is in scope before it exists or outside its block.

**Proof.** After the statement, Rust fixes the local's type to the written type. The same
first-step inherent-method argument as AD-524 applies. The scan refuses any second binding in
the function, so no inner binding can hide the local at a later call.

A typed closure parameter has the same proof at the receiver sites in its own closure body.
The scan records those exact sites. It does not extend the proof to nested items, nested
closures, macro tokens or code outside the closure. Untyped parameters keep the gap. The
same binding, type, macro and configuration refusals apply to the whole enclosing function.

A workspace macro call can pass a nested macro call to its expansion. The nested call can be a
procedural macro that binds a receiver without naming it at the outer call. A macro call with an
identifier followed by `!` in its tokens therefore refuses every receiver proof in that function.
The scan checks nested token groups too. Standard macros already known not to bind surrounding
names keep their existing treatment. This fixes part (b) of #1215.

A call on `p.f` can use the written type of `f` when `p` has a receiver proof, its struct is
exact and non-generic, and `f` is one visible named field. The field and all other fields must
have inert attributes. The field type is a plain path or one reference to it. The scan resolves
the field type in the struct's module, checks that it is exact, and applies the first-step rule
to that type. A `Deref` impl of either type, a tuple field, a field chain, a generic struct,
an alias or a field that a configuration can change keeps the gap. A shared base does not prove
a unique-reference field. The scan does not invent fields made by a macro.

**Measurement.** On #1203, native self-check gaps fall from 101 to 96. The five removed gaps are
the calls in `rust/src/collect.rs` to `edges`, `edges_extracted`, `module_edges`, `impl_edges`
and `declared`. The marked native graph adds the newly observed `rs-flow -> rs-edges` edge. The
result is 63 PASS, 0 FAIL and 20 UNKNOWN, with no violations.

**Tests.** The written local plants fail before the rule. The refusal plants cover shadowing,
closures, macro tokens, gates, a call before the declaration or in its initializer, a nested
block, generic and alias types, `Deref`, and a different receiver form. The plants are in
`tests/test_collector_false_pass_rust_param_receiver.py`.
The typed closure plants fail before their rule. The closure-site and nested-macro mutations are
each caught. The three `fm-passthrough` and `mt-passthrough` plants of #1215 keep their gaps.
The field plants fail before their rule. Mutations of generic, field attribute, base and field
`Deref`, field visibility and receiver-form checks each fail a plant. The field rule closes no
additional self-check pair on this branch without the other authors' calling-side changes.

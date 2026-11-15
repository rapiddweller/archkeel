# AD-524 A call on a typed parameter is an edge in Rust

**Status.** Proposed. Part of #880. Closes #1012. It extends AD-383 (the `self` receiver) and
AD-357 (the pair gap).

**Rule (written before the code).** A method call `x.m(..)` is an edge to the module of the one
inherent member `m` of `T`, and gives no gap, when all of these hold; any other case keeps each
gap of AD-357.
1. `x` is a parameter of the enclosing `fn`, written `x: T`, `x: &T` or `x: &mut T`: a plain
   identifier (`mut` is fine; no `ref`, no `@`, no tuple, no attribute on the parameter), and
   `T` is a plain relative path with lifetime arguments only. A written type is a proof;
   inference is not.
2. The name `x` is bound once in the `fn`, the parameter. A `let`, a pattern of `match`,
   `if let`, `while let` or `for`, a closure or nested `fn` parameter, an item or a `use` that may
   bind it, and any macro call whose tokens name `x` are refusals, except a macro of `std` that
   binds nothing (`println`, `format`, `write`, `assert`, `vec`, ...). If a `macro_rules!`, a
   `use` leaf or rename, or an `extern crate` of the workspace gives such a name to a macro, no
   parameter has a proof. Any other macro call in the `fn` that is not a `macro_rules!` of the
   workspace (a macro with a path, a macro of a crate) refuses every parameter of the `fn`.
3. `T` does not start with a generic parameter of the `fn` or of the `impl`; it is not
   `impl Trait`, `dyn`, `Self`, an alias or a qualified path; it resolves to one struct or enum
   that every configuration has (AD-383 `exact_type`).
4. The `fn` and its `impl` have only inert attributes, and so has every statement, expression,
   arm and block of the `fn`: one `cfg` or unknown attribute in the `fn` refuses all parameters.
   The `fn` is in no gated module and no block, and is not a trait item. The workspace has no `Deref` or `DerefMut` impl for a type of the same name.
5. The member is exact, certainly visible, has the arity of the call, and its `self` form is the
   form of the parameter: `T` and `self`, `&T` and `&self`, `&mut T` and `&mut self`.

**Proof.** The first probe of `x.m()` is the type of `x` as written. An inherent method of `T`
whose `self` has that same form matches at that probe, so no trait method, no deref target and no
auto-ref step can come first, and Rust allows one inherent `m` per type (the AD-383 proof, on a
parameter instead of `self`). What differs from `self` is that a name can be bound again: rules 2
and 3 refuse every way that the scan reads for that. Rule 4 refuses the `&mut T` calling `&self`
form, where a trait impl for `&mut T` could win, and a `Deref` that the scan cannot rule out.
**Not claimed:** a trait method of the same name in scope, or a method on `&T`, cannot win at the
first probe, so they are no refusal.

**Refused forms, each its own plant.** let, inner-block let, closure parameter, match arm, `if
let`, `for`, generic of the `fn` and of the `impl`, `impl Trait`, `dyn Trait`, alias, struct of
the same name in the body, `&mut T` with `&self`, `T` with `&self`, `&&T`, tuple and `ref`
pattern, macro that rebinds, call inside a macro, macro that names the parameter, `use ... as x`,
`Deref` impl, shadowed `std` macro, `cfg` on the `fn` and on the parameter, nested `fn`, gated
module, field of the parameter (slice 3 of the plan).

**Price and gain.** `make self-validate`: native gaps 117 to 113 (4 pairs of the TypeScript
crate), UNKNOWN 20, FAIL 0, violations 0. Three pairs came back after the proof review: their
callers hold a macro that the rules refuse. The proof found a real cycle: `discover.rs:112` calls
`layer.allow_js()`, a method of `Layer` placed in `config.rs`, which imports `discover`; the
method moved to `layer.rs`, the module of its type. The gain is lower than the plan (about 15)
because the largest group (`source: &Source<'_>`) names a type that `macro_rules! object` makes,
which the scan cannot place. Outside a project: each call on a typed parameter whose type and
member are in the workspace stops costing a gap; a proven edge is judged by the contract and may
show a cycle that the gap hid. Calls on locals, fields, closure parameters and chains stay gaps.

**Where.** `scan_params.rs` (reads the parameters; below `scan_receivers.rs`), `scan_receivers.rs`
(frames hold the parameters), `impl_receivers.rs` (the checks of rules 3 to 5), `definitions.rs`.

**Mutations (each run).** Count of bindings ignored: 7 plants fail. Macro tokens ignored: 2.
Generic names ignored: 2. Form check dropped: 2. Block check dropped: 1. `Deref` check dropped:
1. `std` macro shadow by a macro, a `use` leaf (2 plants) dropped: 1. Foreign macro of the `fn`
dropped: 1 (proc macro). Attributes of the body (3 plants) and of the `impl` (2 plants) dropped.

**Plants (46).** 17 fail first: 9 on main (`bc41b134f`) and 8 of the proof review on `b6ae50b8f`
(a `use` rename, a macro of a crate outside the roots, a proc macro, `cfg` on the `impl`, a trait
impl, a statement, an arm, a block). The allowing contract and 28 refusals give the same verdict
before and after. All 36 first sources pass `cargo check`; the review plants are in
`tests/rust_param_review_plants.py`. The tests are in
`tests/test_collector_false_pass_rust_param_receiver.py`.

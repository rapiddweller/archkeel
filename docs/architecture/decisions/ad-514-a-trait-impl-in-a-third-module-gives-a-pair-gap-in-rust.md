# AD-514 A trait impl in a third module gives a pair gap in Rust

**Status.** Proposed. Part of #880. Closes the main class of #1004 and the matching row of #1075.
It extends AD-357.

**Problem.** An impl of a trait for a type runs wherever the types fit, and no `use` brings it
in. Take one crate where `b.rs` holds `impl From<crate::a::Y> for crate::c::S` (`b` defines
neither the trait nor the type), `a.rs` calls `y.into()`, and the rule says `a` must not use `b`.
Deleting `mod b;` fails `a` (E0277), so `a` runs code of `b`. Before this AD the verdict was PASS
on every rule, with no gap. The same holds for `S::from(x)`, the `?` operator, operators, `Deref`,
`Display` and `to_string()`, `for` over `IntoIterator`, `Default::default()`, `==`, `Drop`,
`AsRef`, `TryFrom`, `Index`, a blanket impl over closures, generic dispatch (`fn f<T: Tr>`), and a
method `x.m()` whose only definition is the impl of a local trait for a local type in a third
module. The scan reads no types, so it cannot tell which caller runs which impl.

**Rule (written before the code).**
1. A trait impl is an *orphan* of its module when no path of its head is defined in that module.
   The head is the trait path, the self type, and every path in the generic arguments of both. A
   type parameter of the impl is no path. A path is defined in the module when it resolves to a
   struct, enum, union or trait of the file (also in an inline module), or when it is one name that
   a block around the impl declares as a struct, enum, union or trait.
2. A path that the scan cannot resolve to a definition is not defined in the module: a type alias,
   a name that a glob brings in, a path that does not start in the crate, a type that a macro
   makes. The impl is then an orphan. Strict is allowed, weak is not.
3. For each orphan impl in module `b`, each module that may reach it gets the pair gap `m -> b`.
   The gap is written exactly as the pair gaps of AD-357 and is dropped by the host only when the
   contract lets `m` use `b` and no cycle closes (AD-418). A pair that an edge joins gets no gap:
   the edge decides.
4. The set of modules that may reach the impl is every module of the crate of `b`, and every module
   of each crate that depends on that crate, through any Cargo closure (`depends`, review B2 of
   #1121).

**Proof sketch of the bound (rule 4).** Rust gives an impl no scope: coherence makes it visible to
all code that is type-checked with the crate of the impl linked. So code of crate `K` can run an
impl of crate `X` only when `K` is `X` or `X` is in the Cargo closure of `K`. A module of that set
can hold a value of the self type, or a type argument, without naming it: a function of another
module returns it, a generic parameter carries it, `Default::default()` infers it. The scan has no
type of a value, so no smaller set can be proved. The bound is therefore the whole crate and its
dependents. It is the largest set the rule needs and the smallest the scan can prove.

**What the rule does not claim.** A head path that `b` defines *anchors* the impl in `b`: such an
impl keeps its verdict. This is the class "a method on a value of a type that the caller does not
name" (AD-418, #1004 second form). The impl in the module of the type, the module of the trait and
`impl From<LocalY> for String` (module defines `LocalY`) are in this class, and so is a function-
local impl for a function-local type.

**Open false PASS, not accepted (a pinned plant for each).**
- A value of a type of `b` that `a` gets from another module: `c::make() -> b::Y`, `impl From<Y>
  for String` in `b`, `a` calls `c::make().into()`. Test `an_open_form_stays_a_named_false_pass`.
- An impl that a `macro_rules!` of `b` generates (#1020). The scan reads no item that a macro
  makes. Same test, second plant.
- A trait of a crate outside the workspace that a glob brings in (AD-357, unchanged).

**Price (measured).**
- `make self-validate`: native `63 PASS / 1 FAIL / 19 UNKNOWN`, `124` pinned gaps, shell `22/0/0`.
  The pins do not move. The scan of `native/` found one orphan impl, not none as #1004 said:
  `impl From<Cause> for Reason` in `model/src/receipts.rs`. It moved to `reason.rs`, the module of
  `Reason`, with no change of behavior. Five other impls (`Visitor` in `survey/hazards.rs` and
  `survey/stable.rs`, `Visitor` in `facts/src/envelope.rs`, `Drop` in `snapshot/src/work.rs`,
  `From<PythonVersion> for String` in `facts/src/pyminor.rs`) are anchored by the block rule or by
  the argument rule. A first version of the rule, without these two anchors, flagged all six modules and moved the pins.
- Fixture matrix: 22 runs, none of language Rust and no `.rs` file. No row moves.
- General price: one orphan module gives `N - 1` pair gaps for a crate of `N` modules, plus the
  modules of each dependent crate. The host drops each gap that the contract allows. A contract
  that lets every module use `b` (a shared sink) pays nothing. Any other contract gets UNKNOWN
  until `b` holds no orphan impl or the contract allows the pairs. The cure is to move the impl to
  the module of its type or of its trait.

**Where.** `native/rust/src/orphan_impls.rs` (the rule, one function, called from
`Builder::impl_members`); `scan_definitions.rs` (`trait_impl` and `block_type` read the head
paths and the types of blocks); `impl_globs.rs` (`once_gap`, `depends`). No file of the model, the
core or the report names a language.

**Mutation table (each row was run; the plants are in
`tests/test_collector_false_pass_rust_orphan_impl.py`).**

| Change of the code | Test that fails |
|---|---|
| No gap (the code before this AD) | 17 use-form plants, both contract plants of the pair, the cross-crate plant |
| Callers: the crate of `b` only | the cross-crate plant |
| Head without the argument paths | `impl From<Y> for String` control, and the open form (it becomes a gap) |
| Block declarations ignored | the control for a type that a block declares |
| An unresolved path counts as defined | the plants `a type alias in b` and `a type that a glob brings into b` |

**Plants (28 tests).** 21 fail first on `0a9a20576` (PASS there, no gap): 19 use-form plants, the
plant of a crate that depends on the crate of `b`, and the plant where the contract forbids the
pairs. After the change each gives UNKNOWN. The plant where the contract allows the pairs, the 4
controls (impl in the module of the type, of the trait, function-local, anchored by an argument)
and the 2 open forms give PASS before and after. `transitive_edges_tests.rs` pins the orphan gaps
of the `app -> mid -> leaf` fixture for `impl Trait` and `Box<dyn Trait>`.

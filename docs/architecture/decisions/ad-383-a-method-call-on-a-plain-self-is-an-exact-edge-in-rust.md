# AD-383 A method call on a plain self is an exact edge in Rust

**Status.** Accepted. It amends [AD-357](ad-357-a-method-of-another-module-is-an-edge-or-a-pair-gap-in-rust.md) point 3 for epic #880.

**Rule of Rust.** For `recv.m(..)` the compiler builds the list of the receiver types: the type of
`recv`, then each type that a deref gives. For each type `U` it tries `U`, `&U`, `&mut U`. At each
step an inherent method whose `self` has that type wins over a trait method; the first step with
a match wins. A path `Type::m` takes an inherent member before a trait member. A type has at most
one inherent `m` for one set of type arguments
([method-call expressions](https://doc.rust-lang.org/reference/expressions/method-call-expr.html)).

**Decision.**
1. For a call whose receiver is the plain `self`, the scan records the type path of the enclosing
   `impl` block (inherent or trait), the inline modules of the block, and the `self` form of the
   method (`self`, `&self`, `&mut self`). A path `Self::m` records the same without a form.
2. The first step of `self.m()` is the type of `self` as written. An inherent `m` of `S` with the
   same form matches there, before any trait method or deref target. The call is an `import` edge
   to the module of that member (specifier `self.m` or `Self::m`) and gives no pair gap.
3. A resolution must hold in every configuration. The collector resolves only when all hold; else
   the call keeps each pair gap of AD-357 point 3:
   - The receiver is the plain `self` in a method of an `impl` block, with no free `fn` or `trait`
     between. A closure sees the same `self`. A path `Self::m` needs the same block.
   - The block has no type or const parameter; its type is a plain relative path with no type or
     const argument (a lifetime is allowed); it is not in a body.
   - No `cfg`, `cfg_attr` or other attribute outside an inert list (`allow`, `doc`, `inline`, tool
     attributes and the like) is on the caller block or method, on the member or its block, on an
     enclosing inline module, on the `mod` declaration of the file or of an ancestor file
     (`path` and `macro_use` are inert there), or as an inner attribute of such a file.
   - The type is a struct or an enum with only inert attributes (also `derive`, `repr`,
     `non_exhaustive`), in such a module, and the only item of its name in its file.
   - Exactly one member `m` of `S` is read, with the same form and arity (any for a path), and it
     is visible for certain: `pub`, `pub(crate)` in the crate, `pub(super)` below the parent of the
     block, private below its module. No member means a trait method, a deref target, a macro or a
     file that the scan did not read; two mean a case that is not certain.
   - No block of a type that the scan cannot place, and no `macro_rules!` body that a call expands,
     defines a function `m`.
4. The reply shape and the protocol do not change: the edge is an `import` record as in AD-357.
5. `native/expected-gaps.json` also pins each known violation (rule, sorted subjects, follow-up
   issue). A new or a missing violation, or one without an issue number, fails
   `make self-validate-native`. The gate does not call the network: it checks that a number is
   present, not that the issue exists.

**Problem.** 40 pair gaps made all 10 rules of native/ UNKNOWN; 23 were `self.m()` in `impl S`.
The first version read `cfg` as inert. A review compiled a member under a `cfg` that is off: Rust
called the member of the deref target, and the collector gave an edge to the gated member only.

**Rejected.** (a) Resolve on a unique method name in the workspace: `count`, `bind`, `check` and
`import` are also methods of std and of external traits. (b) Resolve another `self` form
(`&mut self` calls `fn m(&self)`): a trait method can match at an earlier step; a compiled probe
shows it. (c) Resolve `self.field.m()`: only `fn m(self)` matches at the first step of a place, so
the gain is near zero. (d) Read the union of the `cfg` cases: an edge to the member of one case
hides the target of the other. (e) Change the cycle rule: the cycles of a type file and its `impl`
files are real (lead decision L-45). (f) A gap for each member that a macro expands: about 270
name-collision gaps in native/; that is #1020.

**Limit.** A member that a macro expands is no gap yet (#1020); it only blocks the resolution.

**Tests.** `native/rust/src/impl_receivers_tests.rs`, `impl_receivers_cfg_tests.rs`,
`tests/test_collector_native_rust_receivers_compiled.py` (57 compiled and run probe crates),
`tests/test_native_expected_gaps.py`.

**Cost.** native/: 40 pair gaps before, 20 after; all 20 removed gaps were `self.m()` calls.
`NATIVE-NO-MODULE-CYCLES` goes from UNKNOWN to FAIL with 7 module cycles (#1076). The other rules
stay UNKNOWN.

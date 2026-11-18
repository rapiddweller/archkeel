# AD-864 A static store can supply a destructor from another module

Amends AD-806 for values read from static storage. See #1811.

**Reason.** A writer in `b` puts a `Box<dyn Send>` into a static in `slot`.
It then calls `a::run()` without an argument. The reader in `a` takes the box.
When the box leaves scope, Rust runs `b::Y::drop`. The reader and writer both
name `slot`, but neither the reader nor the store needs to name `Y`.
Even a writer in a downstream crate can supply such a value.

**Decision.** When a module can reach a scanned file that declares a static,
retain a dispatch gap to each scanned file with a possible destructor. Use the
existing graph of imports and possible edges, including the reader's own file.
An opaque path can also reach a store. Recheck reach after adding gaps.
A possible destructor supplies a target, not proof of a dependency.

The trait path can be an alias. Check the method in the impl, including a
macro or attribute that can supply it. An unchanged impl with an unconditional
member other than `drop` cannot implement `Drop`. A static can be local to a function.
Do not require a name such as `Box`, `Mutex`, `Drop` or `dyn` in the reader.

**Limit.** File-level reach does not prove which function reads a static or
which values it can store. This can keep gaps for unrelated statics. This
decision covers written statics; it does not establish completeness for
external storage, macro expansions or other ways to transfer ownership.
AD-806 still attributes a directly supplied generic or trait-object argument
to its caller.

**Check.** `test_drop_from_sibling_storage` executes the destructor and checks
the exact forbidden dependency and both cycle levels. A reader with no path
to the store and a type without a destructor are controls.

**Rejected precision cut.** A declared element type can rule out storing a box
directly. It does not rule out a handle or another store behind an accessor.
The tests transfer an address through a real `AtomicU64` and through a real
`OnceLock<Vec<(u32, u32)>>`. A third test uses an `AtomicBool` only as a flag:
a library owns the payload. All three execute the same destructor.

On native, `model.rs::SERIALS` uses `fetch_add(1)`. `pyrepr.rs::ranges` fills
its table from a constant. These are facts about uses, not about either type.
`pyrepr.rs::TABLES` also uses an alias; `std_globals.rs::CELL` wraps `Catalog`.
A narrower result needs evidence of all writers, accessors and escapes. It
must retain the gap when it cannot bind a use or trace the value's origin.

**Measurement.** Against `9ec92f15f`, the native scan keeps all 92 rule
statuses (81 PASS, 11 UNKNOWN) and zero violations. It reports 23,114 gaps,
up from 22,599 (+526, −11). Of the added rows, 316 directly name the possible
destructor in `snapshot.test_tree` and 184 name `snapshot.work`. These are
destructor targets, not counts of distinct storage declarations.
The pin does not accept the increase.

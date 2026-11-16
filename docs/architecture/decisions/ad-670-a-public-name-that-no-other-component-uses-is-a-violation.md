# AD-670 A public name that no other component uses is a violation

**Status.** Accepted (owner order: the "best ratio" prevention bundle, measure 6; new checks land
as rules of the self-contract, and their current FAIL rows stay visible). Part of #880.

**Reason.**
- The compiler counts a public item as used when its own crate, an example or a test uses it.
- `native/api_baseline.json` records a change of the public surface, not whether an item is needed.
- The hygiene audit found about 70 public items that no other crate uses, and 511 lines of dead
  examples that kept items alive.
- AD-622 already removes a contract `public` entry that no other component names. The code had no
  such rule.

**Decision.**
1. Contract 3.16.0 adds the rule kind `unused_public`.
   - `source` selects the modules.
   - `item_kinds` (optional) selects the kinds of item.
   - `external_users` names an item that a consumer outside the scan uses (`module:Name`, the
     consumer and a reason). This is the only exemption.
2. The rule judges each module-level symbol below `source` that the collector states as declared
   public. A method, a field and a variant are members, not items.
3. Another component uses an item when one of its imports names the item: by the item's own name
   in its module, or by a hop of a re-export route (AD-604). Another target of the same package
   (a binary) counts too (AD-622).
4. An item with no proven user is a violation, except in these cases, where it is undecided (it
   holds back a PASS and decides nothing):
   - another component takes the item's module by a glob, by a whole-module import whose names
     the collector does not write as records of their own (AD-604 `namespace_uses`), or through a
     macro body. An item that such an open module takes in by name is undecided too.
   - another component imports the item's name through a route that is not proven.
   - the item is a type (a class, an alias or a macro). A signature of a used item may need it,
     and no collector states resolved signature types yet.
5. A PASS needs a collector that states every public symbol (`symbol_facts`). The Rust collector
   does not state every one (AD-351), so on Rust the rule gives FAIL or UNKNOWN, never PASS. A
   collector that states no dependency symbols holds the rule (a missing name would look unused).
6. The rule reads every import of every module: each coverage gap and each pair gap can hold it.

**Why it is sound.**
- A use counts only when an import record names the item.
- Each way that a use can stay unseen gives UNKNOWN: a glob, a module, a macro, a route that is
  not proven, a signature, or a symbol record that is missing.
- So a PASS means that every public item that the collector states has a proven user, and that
  the collector states every public item.

**Self-contract.** `NATIVE-PUBLIC-HAS-A-USER` judges the functions, constants and statics of every
native crate. Types wait for signature facts of the Rust collector; this is a named gap and the
next step (#1402).
- Native self-check: before 89 PASS, 4 FAIL, 0 UNKNOWN (27 violations). After: 89 PASS, 5 FAIL,
  0 UNKNOWN (48 violations). The rule is FAIL with 21 rows, pinned with #1402:
  - `facts.schema`: 7 rows;
  - `contract.policy`: 5 rows;
  - `snapshot.work` and `snapshot.test_tree`: 5 rows;
  - `pyast.node`: 2 rows;
  - `facts.nullable`, `facts.pyrepr` and `collect`: 1 row each.
- The first build of the rule itself broke the self-contract, and the self-check showed each
  break. All were fixed in code before the merge, with no pin:
  - two modules had no owner, and the public entries and ports were not declared;
  - there was a module cycle `graph -> model -> pair_gaps -> proof -> published -> graph`. The
    item list moved to `published_items.rs`.
  - there were four clones, and `scope.rs` had 503 lines.
- The shell contract (Python) would show 20 rows. Python has no visibility between module and
  public, so a helper that another module of the same component uses cannot be narrowed. The
  owner decides whether the rule judges Python by module or by component before the shell
  contract adopts it.

**Collector limit found.** `lib.rs` of the Rust collector declares both `mod reply` and
`pub fn reply`. The collector resolves `use archkeel_rust_collector::reply` to the module only. The
rule therefore judges an item `x` of `P` as undecided when another component imports the module
`P.x` as a whole: a whole-module import may name the item too.

**Tests.**
- `tests/test_cli_native_unused_public.py`: Rust plants that rustc accepts, and Python plants that
  python3.12 runs.
- `native/contract/src/unused_public_tests.rs`.

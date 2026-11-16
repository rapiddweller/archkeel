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
native crate. Types wait for signature facts of the Rust collector (named gap, issue below).

**Tests.**
- `tests/test_cli_native_unused_public.py`: Rust plants that rustc accepts, and Python plants that
  python3.12 runs.
- `native/contract/src/unused_public_tests.rs`.

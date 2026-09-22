# The target-first loop

[Onboarding](https://github.com/rapiddweller/archkeel/blob/main/docs/onboarding.md) ends once
the contract is decided and `archkeel report` shows the architecture's own distance from that
decision as violations. It says a remaining `rule.violated` is follow-up code work and stops
there. This page is that follow-up: how to run a repository whose target states more than the
code does, on purpose, for as long as the refactoring it describes takes — gate CI on the
difference, keep the target from drifting toward the code instead of the other way round, work
the backlog down, and land the interfaces the target already names.

Every command below runs on a working copy of `fixtures/F-architecture`, the shop sample, with
one addition already in flight and the diffs shown inline, so the whole page is reproducible.
The sample itself commits clean; the additions are what a refactoring in progress looks like
before it converges on its target.

## 1. Write the target, not a description

`archkeel init` drafts a contract that describes the code: one component per subpackage,
`public` entries for what another component already imports, no dependency decided. A
target-first contract goes further, once the architect decides it: a `requires` or
`allowed_dependency` entry for an edge the refactoring will need before any module crosses it,
and a `public` entry only for an interface that already exists. An interface the refactoring has
not built yet belongs in `planned` instead — the same `pkg.module`/`pkg.module:Name` shape as
`public`, disjoint from it. `validate` stays silent until a caller reaches the entry, even if the
module already exists (AD-56, AD-79). Declaring it `public` before it exists is a worse mistake than it looks:
`interface.missing` reads identically whether the entry is a typo or a facade nobody has written
yet. A violation baseline cannot hide either validation diagnostic.

The architect decides `app` will eventually expose a small report facade the refactoring has not
written yet:

```diff
       "packages": ["shop.app"],
       "public": ["shop.app.orders:place_order"],
+      "planned": ["shop.app.future:NotBuiltYet"],
```

```
$ archkeel validate --json
exit_code: 0
diagnostics: []
```

Naming the same entry under `public` instead of `planned` is the mistake the split exists to
catch:

`archkeel validate --json` exits 2 with:

```json
{
  "code": "interface.missing",
  "subject": "shop.app.future:NotBuiltYet",
  "unknown_claim": "The public entry's module has not been scanned; it does not exist yet.",
  "remedy": "Build the module, correct a typo, or move the entry to planned until it exists."
}
```

When a component owns several root packages, keep ownership in `packages` and declare the
intended physical home separately:

```json
{
  "label": "orders",
  "namespace": "shop.orders",
  "packages": ["shop.orders", "shop.order_rules"]
}
```

Owned modules below `shop.order_rules` are then baselineable `module.placement` findings. The
namespace is optional, so older contracts remain ownership-only.

### Choose type ownership before placement

`init` drafts package components. It does not infer a foundation or decide where classes belong.
Ask who owns a shared type first. `foundation` is not the default home for domain enums or
Pydantic models. If the architect assigns those types to `shop.model.vocabulary`, keep that
decision in the existing `symbol_placement` rule:

```json
{
  "id": "DOMAIN-TYPES-IN-MODEL",
  "kind": "symbol_placement",
  "source": "shop",
  "class_kinds": ["enum", "pydantic_model"],
  "exact_sources": ["shop.model.vocabulary"],
  "rationale": "The model component owns shared domain vocabulary; foundation stays generic.",
  "provenance": ["docs/architecture/architecture.md"],
  "decided_by": "architect"
}
```

`exact_sources` names one module. Use `allowed_sources` when the chosen owner is a package
subtree. Run `archkeel validate` after adding the rule; matching classes in `shop.foundation`
are then reported as `rule.violated`. The `class-a-symbol-placement` demo shows the same
exact-module mechanism on the shop sample.

## 2. Get the first red report, and read it without drowning

Once the target states more than the code has reached, `report` is red by design. On a repository
of any size the full page — component flow, communication, review claims, size and coupling
alongside the violations — is not something a reviewer or an agent reads start to end every
time. `report --only violations` drops everything but the violations table; `--rule <id>` and
`--component <label>` narrow that table further and combine as an intersection (AD-60). None of
the three change what was judged: `declared_rules`, the violation counts and the exit code stay
computed from every violation, filtered or not
([reference.md](https://github.com/rapiddweller/archkeel/blob/main/docs/reference.md#narrowing-a-report)).

The refactoring in progress has moved a report use case into `OrderRepository` ahead of the
use-case layer the target says should own it, reaching directly for `Money`:

```diff
-from shop.model.entities import Order
+from shop.model.entities import Money, Order
 from shop.store.backend import order_path, read_document, write_document
 from shop.store.codec import decode, encode


 class OrderRepository:
     ...
     def load(self, order_id: str) -> Order:
         return decode(read_document(order_path(self._root, order_id)))
+
+    def total_due(self, order_id: str) -> Money:
+        """A report use case reaches this directly while the refactor moves it to app."""
+        return self.load(order_id).total()
```

```
$ archkeel report --only violations --json
declared_rules: FAIL
violations_by_rule: [["DEP-STORE-NO-MONEY", 1]]
violations_by_component_pair: [["store", "model", 1]]
```

```
$ archkeel report --only violations --rule DEP-STORE-NO-MONEY --json
$ archkeel report --only violations --component store --json
```

Both narrow `filtered_violations` to the same one record; a misspelled `--rule` or `--component`
is a named `filter_unknown` at exit 2, never a silently empty page.

## 3. Freeze what is there

Do not describe the code in the contract to make `validate` pass — that is what a target-first
contract exists not to do. Freeze the violations instead (AD-52):

```
$ archkeel validate --baseline known-violations.json --write-baseline
```

```json
{
  "schema_version": "1.1.0",
  "violations": [
    { "count": 1, "rules": ["DEP-STORE-NO-MONEY"],
      "subjects": ["shop.model.entities.Money", "shop.store.repository"] }
  ]
}
```

Review this file the way a diff of the contract itself is reviewed, and commit it. Counts must
match the observation exactly: a higher one is a new violation, a lower one a violation someone
already fixed, both failing the gate. When updating an existing file, `--write-baseline` compares
first: resolved-only drift may be written, while new or increased fingerprints refuse the write
unless `--accept-new` is explicit. Results expose deterministic `baseline_new` and
`baseline_resolved` counts. A budget allowed to *exceed* the code — "no more than N
violations of this rule" — would be worse than exact counting: it lets a violation someone
removed go unreported, the same way an unbounded margin hides a regression a stricter one would
catch. Exactness is what makes shrinking the file part of the change that shrinks it, not a
separate bookkeeping step (AD-52).

## 4. Gate CI

The gate is the same command, without `--write-baseline`:

```
$ archkeel validate --baseline known-violations.json
exit_code: 0
declared_rules: FAIL
failures: []
```

Exit 0 with `declared_rules: FAIL` is not a bug to work around: the violations are still there
and still reported, and the baseline is what says they are the ones already accounted for.
The gate fails — exit 1, named in `failures` — only on a violation the file does not state, or
one it states that nobody violates any more. Every other diagnostic still exits 2, exactly as
without `--baseline`. A CI job needs nothing beyond the command already in the repository's own
`check` job:

The confirmed `private_crossings` ratchet remains private cross-package imports. Named UNKNOWN
private-attribute accesses from untyped or `Any` parameters are measured separately as
`untyped_private_accesses` and in `unknowns`; no runtime component owner is inferred (AD-83).

```yaml
- name: Hold the architecture to its target
  run: uv run --locked archkeel validate --baseline known-violations.json
```

For a project gate, keep the same fail-closed shape in the repository's `Makefile`: one target
names the project's checks and the architecture check as prerequisites. There is no pipe to hide a
status and no generic Archkeel command configuration:

```make
.PHONY: gate
gate: project-check architecture-check

project-check:
	uv run --locked pytest -q

architecture-check:
	uv run --locked archkeel validate --baseline known-violations.json
```

CI runs `make gate`. A deliberately failing `project-check` must make `make gate` nonzero; later
prerequisites must not turn that failure into success.

## 5. Keep the target from moving

The easiest way to make a violation disappear is to widen the rule that names it instead of
fixing the code — add an `allowed_sources` entry, a `requires` edge, drop a rule — in the same
change. `--against <ref>` classifies every difference from the contract at that Git revision as a
widening (a new permission or a dropped restriction) or a narrowing, its harmless reverse; a
widening fails unless `--amendment` names a file that an architect wrote, binding its exact
before/after contract digests (AD-61, #11). Point it at the branch's own base, the commit CI
would otherwise diff against.

Instead of removing the `Money` reach above, an agent under time pressure could "fix" the
violation like this:

```diff
       "target_symbol": "Money",
       "include_type_checking": true,
+      "allowed_sources": ["shop.store.repository"],
       "rationale": "Persistence serialises whole orders and must not compute or interpret money amounts itself.",
```

```
$ archkeel validate --against <base>
exit_code: 1
failures: ["rule DEP-STORE-NO-MONEY.allowed_sources gained 'shop.store.repository'"]
```

The run fails, naming exactly the field it found — an unrecognised or unenumerated difference
would fail the same way rather than pass silently (the module and `label`/`role` on a component,
`through` on a `requires` entry, all of `declarations`). The right response is almost always to
revert the contract and fix the code instead, which is step 7. When the architect genuinely
decides the exemption belongs in the target — a transitional read, kept only until the next
change lands — the decision is recorded, not waved through:

```
$ archkeel validate --against <base> --amendment widening.json \
    --write-amendment --decided-by "Jordan (architect)" --rationale \
    "Repository.total_due is a transitional read; the report use case moves to app in the next change."
```

```json
{
  "schema_version": "1.0.0",
  "before_digest": "ddb44729361818e91d9b77dab563f924dfa08dff3e13ce2bf0ba9565e5e55656",
  "after_digest": "f4a6b864e68d9605a6e3c6467fd6ea8fa2b9c9931cf40f00c23b08d245490a99",
  "decided_by": "Jordan (architect)",
  "rationale": "Repository.total_due is a transitional read; the report use case moves to app in the next change."
}
```

```
$ archkeel validate --against <base> --amendment widening.json
exit_code: 0
```

An amendment written for one change does not verify against a different one — its digests will
not match — so it cannot be reused to wave through an unrelated later widening. Never widen the
contract in the same change that removes the violation it names: fix the code, or get an
amendment from the architect who owns the target.

## 6. Draw the target

A contract page's marked graph, `<!-- archkeel-component-graph -->`, draws what the code does.
Under a target-first contract, what the code does always includes the edges the target still
forbids — known debt that graph would draw as if it belonged. A second marker,
`<!-- archkeel-target-graph -->`, draws what the contract permits instead: every pair a
`requires` entry or an `allowed_dependency` rule decides (AD-57). The shop sample's page carries
both, and today they agree — the target has no headroom the code has not used yet.

Deciding a pair ahead of the code that will use it is exactly when they stop agreeing. The
architect decides `cli` may construct a default order directly, ahead of the use case that will
call it:

```diff
-      "id": "DEP-CLI-NO-MODEL",
-      "kind": "forbidden_dependency",
-      "source": "shop.cli",
-      "target": "shop.model",
-      "include_type_checking": true,
-      "rationale": "The composition root reaches domain values only through the use cases it calls.",
+      "id": "DEP-CLI-ALLOWS-MODEL",
+      "kind": "allowed_dependency",
+      "source": "shop.cli",
+      "target": "shop.model",
+      "rationale": "The composition root may construct a default order directly, ahead of the use case that will call it; nothing does yet.",
```

`archkeel validate --json` exits 2 with:

```json
{
  "code": "graph.drift",
  "subject": "docs/architecture/shop.md (target graph)",
  "unknown_claim": "The marked target graph differs from the edges the contract permits; edges gone from contract (drawn, not permitted): none; edges new in contract (permitted, not drawn): cli->model."
}
```

The observed graph is untouched — the diagnostic's subject names the target marker, not the
observed one — and `--write-graph` regenerates only that block:

```
$ archkeel validate --write-graph --json
artifact: docs/architecture/shop.md
diagnostics: []
```

```diff
 flowchart LR
     app --> model
     app --> store
     cli --> app
+    cli --> model
     cli --> render
     render --> model
     store --> model
```

A page whose target block has drifted into a `subgraph`, a labeled edge or a style is left to a
hand edit instead, the same remedy the observed marker's writer already gives (AD-46, AD-57).

## 7. Work the backlog down

Fix the violation from step 2 by removing the reach, not by widening the rule:

```diff
-from shop.model.entities import Money, Order
+from shop.model.entities import Order

-    def total_due(self, order_id: str) -> Money:
-        """A report use case reaches this directly while the refactor moves it to app."""
-        return self.load(order_id).total()
```

The baseline shrinks in the same change:

```
$ archkeel validate --baseline known-violations.json --write-baseline
declared_rules: PASS
```

```json
{ "schema_version": "1.1.0", "violations": [] }
```

An overstated baseline fails the gate exactly as an understated one does, symmetrically: running
the old, one-entry file against the now-fixed code is a `resolved violation`, not silence. A
resolved-only update may rewrite the file with `--write-baseline`; accepting a new or increased
fingerprint requires `--write-baseline --accept-new` —

```
$ archkeel validate --baseline known-violations.json   # the stale file, not rewritten
exit_code: 1
failures: ["resolved violation: DEP-STORE-NO-MONEY | shop.model.entities.Money shop.store.repository (0 observed, 1 in the baseline); rewrite the baseline with --write-baseline"]
```

— because a budget allowed to run ahead of the code is exactly the hole a padded baseline
exploits (AD-52, AD-61): the file must state today's debt, not yesterday's.

If the resolved row is schema 1.1 and carries a `source`/`target` role, its subjects prove the
importer and the exact public module or symbol it reached. `validate --baseline` keeps the
resolved failure but suppresses only that matching `interface.unused` twin, and says to remove
the now-unreached entry. A 1.0 baseline or an unrelated role cannot prove the narrowing, so the
normal diagnostic remains (AD-85, #80).

On a backlog larger than one entry, `violations_by_rule` and `violations_by_component_pair` in
`report --json` rank it by weight without decoding anything else (AD-51); `--rule` and
`--component` then isolate one slice to work, the same flags used to read the first report in
step 2. An agent building its own dashboard on top of `architecture.json` reads typed rows with
`archkeel.api.load_violations`, the one supported facade instead of decoding the columnar file
directly (AD-54, AD-64;
[reference.md](https://github.com/rapiddweller/archkeel/blob/main/docs/reference.md#reading-a-reports-violations)).

## 8. Land a planned interface

Once the refactoring writes and a caller reaches the facade step 1 only promised, land it:

```python
def NotBuiltYet() -> str:
    return "built"
```

`archkeel validate --json` exits 2 with `interface.planned_built`:

```json
{
  "code": "interface.planned_built",
  "subject": "shop.app.future:NotBuiltYet",
  "unknown_claim": "The planned entry's module has been scanned; it is no longer planned.",
  "remedy": "Move the entry to public and drop it from planned."
}
```

The remedy is the whole fix — move the entry, drop it from `planned`. A built but unused module
does not produce this diagnostic; it is still target work (AD-79).

```diff
-      "public": ["shop.app.orders:place_order"],
-      "planned": ["shop.app.future:NotBuiltYet"],
+      "public": ["shop.app.orders:place_order", "shop.app.future:NotBuiltYet"],
```

`archkeel validate --json` exits 2 again, this time with:

```json
{
  "code": "interface.unused",
  "subject": "shop.app.future:NotBuiltYet",
  "unknown_claim": "No cross-component import and no declared facade signature reaches this public entry."
}
```

This is not particular to landing a planned entry — it is `interface_boundary`'s ordinary reading
of any declared `public` name nothing yet reaches (AD-9), and it clears the same way any such
entry does: once a caller actually crosses, or once one of the component's own declared facade
signatures names the type, which exposes it to every consumer of that signature without an
import of its own (AD-65).

## The loop repeats

Fixing one violation and shrinking the baseline by one entry is the whole cycle: return to step 2
for the next slice — by rule, by component, or by weight from `violations_by_rule` — until
`validate --baseline` passes on an empty file. At that point the target and the code are the same
thing, and the target contract is free to state the next place they should differ.

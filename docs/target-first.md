# The target-first loop

[Onboarding](https://github.com/rapiddweller/archkeel/blob/main/docs/onboarding.md)
ends with a decided contract. Remaining `rule.violated` findings are code work.
Use this loop to baseline that debt, gate new violations and contract widening,
then reduce the baseline as refactoring reaches the target.

Every command below runs on a working copy of `fixtures/F-architecture`, the shop sample, with
one addition already in flight and the diffs shown inline, so the whole page is reproducible.
Base validation exits 0, but the store rule is UNKNOWN: `shop.store` re-exports an interface
and has no child owner. Before claiming PASS, add `"exact_modules": ["shop.store"]` to the
existing `repository` component in `shop/store/architecture-contract.json`. This is the
`ownership-exact-module-positive` demo overlay; it assigns only the initializer. The additions
below then show a refactoring in progress before it converges on its target.

## 1. Write the target, not a description

`archkeel init` drafts observed components and interfaces, leaving dependencies
undecided. The architect can approve future edges with `requires` or
`allowed_dependency`. Existing interfaces belong in `public`; unbuilt interfaces
belong in disjoint `planned` entries with the same selector shape.

A planned entry remains quiet until reached, even if its module already exists
(AD-56, AD-79). An unscanned public entry produces `interface.missing`, whether
it is a typo or future work; violation baselines cannot hide diagnostics.
Re-export and DTO field checks follow the [rule catalog](rules.md#class-a-deterministic-rules).

When a refactoring moves a module, declare the old path in `declarations.compat` with its target
and lifetime. A `migration` shim is visible remaining work while it protects callers; promote it
to `permanent` only when that compatibility surface is intentional (AD-87).

Use the deepest existing mounted contract's optional `declarations.modules` list to name exact
Python files and their intended responsibilities. Target navigation groups a file beneath the
deepest uniquely matching declared component within its declaring scope, using only the configured
roots and namespace to derive a Python module name. This is navigation, not module ownership, and
does not depend on source presence or parse success. Ambiguous scopes or namespace anchors stay
unresolved. Missing files also appear under `Diff` as absent targets. Keep semantic ownership in
`components[].packages`.

```json
{
  "declarations": {
    "modules": [
      {
        "path": "src/shop/orders/service.py",
        "responsibility": "Apply order rules and persist accepted orders."
      }
    ]
  }
}
```

Facade and coupling budgets can target fewer names than today's interfaces expose.
`--write-baseline` records accepted names; `over_target` reports the gap and changed
name sets fail. Raising `max_names` or accepting a new name widens `--against`.
See [budget syntax](rules.md#class-b-regression-checks) (AD-99).

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

Use `root_layout` when the package root itself must expose only an exact set of immediate
packages or modules; missing future children remain target work.

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

Use `report --only violations`, optionally intersected with `--rule <id>` and
`--component <label>`, to review one slice. Filters retain global verdicts,
counts and exit status ([reference](reference.md#narrowing-a-report), AD-60).

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

Keep the target; baseline existing violations (AD-52):

```
$ archkeel validate --baseline known-violations.json --write-baseline
```

```json
{
  "schema_version": "1.3.0",
  "budgets": {},
  "violations": [
    { "count": 1, "rules": ["DEP-STORE-NO-MONEY"],
      "subjects": ["shop.model.entities.Money", "shop.store.repository"] }
  ]
}
```

The path is relative to `--root`, like the contract: a second code base in `mobile/`, run from
the repository root, freezes its own debt with `archkeel validate --root mobile --baseline
known-violations.json --write-baseline`, which writes `mobile/known-violations.json`. An absolute
path inside the root works too; one outside it is `baseline.invalid`, exit 2 (AD-103).

Review and commit the baseline. Counts must match exactly: increased counts are
new violations; decreased counts require cleanup. `--write-baseline` compares an
existing file before writing. Resolved-only drift and contracted cycles can be
written; new/increased fingerprints need explicit `--accept-new` (AD-98, AD-106).
`baseline_new` and `baseline_resolved` count changed fingerprints, not occurrences.
Shrink the baseline in the same change that removes its debt.

## 4. Gate CI

The gate is the same command, without `--write-baseline`:

```
$ archkeel validate --baseline known-violations.json
exit_code: 0
declared_rules: FAIL
failures: []
```

Exit 0 accepts the recorded debt while `declared_rules: FAIL` still reports it.
New or resolved debt fails with exit 1; other diagnostics retain exit 2.
Add this command to the existing CI check:

```yaml
- name: Hold the architecture to its target
  run: uv run --locked archkeel validate --baseline known-violations.json
```

One Make target should require project checks and architecture validation:

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

### Govern the tests as a second scope

The product scan reads only its own roots, and its scan-complete reason says so. When the
tests' layout and imports are part of the target, give them a second configuration beside
`archkeel.toml` with their own namespace and contract, and gate it as its own target (AD-101):

```toml
# archkeel-tests.toml
[scan]
roots = ["tests"]
namespace = "tests"
contract = "tests/architecture-contract.json"
```

```make
architecture-check:
	uv run --locked archkeel validate --baseline known-violations.json
	uv run --locked archkeel validate --config archkeel-tests.toml
```

The existing rule kinds cover the deterministic part: `root_layout` and `complete_assignment`
for the suite layout, `symbol_placement` for where helper classes live, `complete_requires`
for which suite imports which, and `external_dependency_scope` for which suites import the
product. The shop sample's [test contract](../fixtures/F-architecture/docs/architecture/tests.md)
is a worked example; the `test-scope-*` rows in [the demo catalog](architecture-demo.md) show a
moved helper, a suite crossing and a unit test importing the product each fail at their file.
Duplicated tests and result equivalence stay with the test suite and its oracle
([known limits](known-limits.md)).

`report` writes to the same default path whichever configuration it reads, so give the test
scope's report its own, or it replaces the product report:

```
archkeel report --config archkeel-tests.toml --output test-artifacts/tests/architecture.json
```

## 5. Keep the target from moving

`validate --against <ref>` rejects new permissions or removed restrictions unless
an architect's amendment binds the exact policy change (AD-61). Pure recognized
package renames compare under their new names; additional widening still fails
(AD-105). Compare with the branch's base commit.

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

The failure names the changed field. Unclassified changes also fail closed.
Fix the code, or record the architect's transitional permission:

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

The amendment applies only to its bound change. A different change needs a new
architect decision and matching digests.

### A new contract is one widening

A contract the base does not hold yet has nothing to be compared with: a second scope's first
merge request, such as a Flutter app under `mobile/` with its own `archkeel.toml` and contract,
or a contract moved to a new path. It is one widening, named by its path in the repository
(AD-104):

```
$ archkeel validate --root mobile --against <base>
exit_code: 1
failures: ["contract introduced: mobile/architecture-contract.json does not exist at <base>"]
```

The architect records the introduction like any other widening, and the gate passes with it:

```
$ archkeel validate --root mobile --against <base> --amendment mobile/introduced.json \
    --write-amendment --decided-by "Jordan (architect)" --rationale \
    "The mobile app gets its own contract."
$ archkeel validate --root mobile --against <base> --amendment mobile/introduced.json
exit_code: 0
```

Run the same `--against` gate for new and moved scopes; do not skip missing base contracts.

## 6. Draw the target

`<!-- archkeel-component-graph -->` draws observed imports.
`<!-- archkeel-target-graph -->` draws permissions from `requires` and
`allowed_dependency` (AD-57). The shop page carries both; they currently agree.

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

The diagnostic names the Target marker; `--write-graph` updates that block:

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
{ "schema_version": "1.3.0", "budgets": {}, "violations": [] }
```

The stale baseline still fails after the fix:

```
$ archkeel validate --baseline known-violations.json   # the stale file, not rewritten
exit_code: 1
failures: ["resolved violation: DEP-STORE-NO-MONEY | shop.model.entities.Money shop.store.repository (0 observed, 1 in the baseline); rewrite the baseline with --write-baseline"]
```

Rewrite resolved-only drift with `--write-baseline`. New/increased fingerprints
require `--write-baseline --accept-new` after an explicit decision.

If the resolved row is schema 1.1 and carries a `source`/`target` role, its subjects prove the
importer and the exact public module or symbol it reached. `validate --baseline` keeps the
resolved failure but suppresses only that matching `interface.unused` twin, and says to remove
the now-unreached entry. A 1.0 baseline or an unrelated role cannot prove the narrowing, so the
normal diagnostic remains (AD-85, #80).

Rank larger backlogs with `violations_by_rule` or `violations_by_component_pair`,
then filter one slice. External consumers use typed `archkeel.api.load_violations`
instead of decoding the columnar file ([reference](reference.md#reading-a-reports-violations), AD-64).

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

A public name needs a cross-component caller or a declared facade signature that
exposes its type (AD-9, AD-65). Promotion alone does not prove use.

## The loop repeats

Return to step 2 for the next slice. Fix its code and update the baseline together
until no accepted violation debt remains. Read UNKNOWN and review unmeasured intent
before declaring the target complete.

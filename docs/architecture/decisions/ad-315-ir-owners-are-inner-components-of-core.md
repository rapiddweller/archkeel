# AD-315 IR owners are inner components of Core

**Decision.** The `ir` component of Core has four new owners: `architecture`, `evidence`, `wire` and
`views`. Each owner is an inner component in `docs/architecture/contracts/ir.json`. They replace the
inner component `governance`. They are not new top-level packages.

The inner components `facts`, `facts-codec`, `protocol`, `profiles`, `dependency-policy` and
`contract-version` stay as they are. Together they own the source facts and the analyzer-facing files.

Each new owner lists its modules with `exact_modules`. The package module `archkeel.ir` belongs to
`architecture`. No file moves in this decision. A later step can move the files into subpackages of
`archkeel.ir` and replace `exact_modules` with `packages`.

| Owner | Can require |
| --- | --- |
| `architecture` | `facts`, `profiles`, `dependency-policy`, `contract-version` |
| `evidence` | `architecture`, `facts`, `facts-codec`, `dependency-policy` |
| `wire` | `architecture`, `facts`, `facts-codec`, `profiles`, `contract-version`, `dependency-policy` |
| `views` | `architecture`, `evidence`, `wire`, `facts`, `dependency-policy` |

An owner can import only the components in its row. A new import needs a new `requires` entry with
a reason. This table has no cycle.

[`docs/architecture/ir-owners.md`](../ir-owners.md) shows the owners, their module counts and the
permitted imports as a Mermaid graph. The test `tests/test_ir_owners.py` generates it from `ir.json`.

`parse_dependency_selector` and the selector grammar move from `codec_contract` to `dependency`.
`decisions` (`evidence`) imported `codec_contract` (`wire`) only for this function. It was the one
import against the table. The grammar reads `Record` and `RecordData`, so `dependency-policy` needs
no new `requires`. `codec_contract` and the `codec` facade import the grammar from `dependency`.
The error text and the order of the checks stay the same for every input.

Two private names that crossed owners become public names: `rule_receipt_complete` in `decisions`
and `validate_module_target_path` in `architecture_graph`.

**Reason.** One owner for each concept lets a reader and a rule find the right module. The old
component `governance` held 46 modules for several reasons to change. Epic #880 needs these owners
before a collector or a fact store changes.

**Supersedes.** This decision replaces three passages, only for owners inside `ir`:
- `target/design.md`: "Do not mandate seven new physical packages" (IR governance row).
- `target/design.md`: "no speculative package migration" (`ir` row).
- AD-239: "Rejected: a codec package".

Owner subpackages inside `ir` are now allowed. A codec package outside `ir`, a registry, injected
callbacks and lazy imports stay rejected.

**Rejected.** New top-level packages: each one needs its own public interface. One `governance`
component: it shows no direction between the concepts.

**Limit.** This decision moves no file and changes no verdict. The root contract keeps the `ir`
component and its public paths. It changes the text of one rule rationale. The v2 amendment
`ad-315-ir-owners-amendment.json` binds both policies. The `exact_modules` lists name the current
module paths.

**Check.** `tests/test_ir_owners.py` reads the owner modules from `ir.json`. It checks the table
and every import in these modules, also inside functions. It checks that `decisions` does not import
`codec_contract`. It checks that the page is the same as the contract. The marked-graph check of
`archkeel validate` reads the root contract only, so the page has its own markers.
`tests/test_typed_dependency_api.py` checks the error text and order of the
selector grammar. `tests/test_codec_compatibility.py` checks the `codec` facade.
`make self-validate` and `make against BASE=origin/main` check the contract.

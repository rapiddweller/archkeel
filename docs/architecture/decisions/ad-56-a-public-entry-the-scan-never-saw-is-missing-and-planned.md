# AD-56 A public entry the scan never saw is missing, and planned exempts target work

`interface_diagnostics` splits an unused `public` entry by whether its module was ever scanned.
One the scan never saw is `interface.missing`: the contract names something that does not exist,
whether that is a typo or a facade a refactoring has not built. One the scan saw but nothing
imports stays `interface.unused`, exactly as before; a used entry is checked against neither,
so this only narrows the case that already carried no evidence. A `pkg.module:Name` entry is
judged by its module alone, never by looking its name up in `symbols`: that section records only
classes and functions, and an unmatched name there would as easily be a module-level constant or
a `TypeAlias` the scan cannot see as a genuine typo, so asserting "missing" from it would trade
one false signal for another. A component gains an optional `planned` list, the same
`pkg.module`/`pkg.module:Name` shape as `public` and disjoint from it: an entry there whose module
the scan has not seen is target work and produces nothing. A built module is also target work until
an import or declared facade signature reaches the entry; then `interface.planned_built` tells the
architect to move it to `public` and drop it from `planned` (AD-79). `planned` needs no declared
`public` of its own, since an architect may name a facade before
the component has any live interface to pair it with, and its entries are held to the same
ownership (`reference.public_owner`) and underscore (`reference.public_underscore`) checks as
`public`'s, by reusing the same checks rather than writing a second pair for a second list.
`planned` is never projected into the observation and the analyzer is untouched -
`ANALYZER_VERSION` does not move — because every one of these checks reads records the scan
already produces, `modules` for existence and `imports` for usage, and a target that does not
exist yet has nothing for a scan to observe about it.

Reason: issue #10 — Archkeel is used to write a target architecture first and let a refactoring
converge on it, which means naming interfaces, such as a facade `io.api`, that do not exist yet.
Before this, a component whose `public` named an unbuilt facade and one with a genuine typo
produced the identical `interface.unused` finding, so a baseline (AD-52) could freeze either one
as "known debt" and a reviewer had no way to tell a promise from a mistake short of reading every
source file by hand.

Rejected: `"planned": true` on a `public` entry, the issue's first suggestion, because AD-9's
`public` entries are plain strings and AD-50 already rejected turning them into objects for the
same reason — it breaks every existing contract for a field most contracts write per module, to
carry one bit only some entries need. A `planned_public` list whose entries must also appear in
`public`, the issue's other suggestion in the shape that keeps them listed twice: it needs its own
consistency rule, a new diagnostic for a `planned_public` entry `public` has never heard of, and a
contract can still drift the two apart by editing one list without the other. `planned`, disjoint
from `public`, needs neither: an entry lives in exactly one list, and a contract that moves it from
one to the other cannot leave two copies to disagree. Checking a `:Name` entry's name against
`symbols` for a sharper "missing" verdict, because `symbols` records only classes and functions,
so a module-level constant or `TypeAlias` would read as missing forever, even after it exists.
Projecting `planned` into the observation and letting `agent_decisions` count it, so a `planned`
entry would need no second check once built: this is a `validate`-time judgment about what a
contract still promises, not a fact the scan observes, and projecting it would have cost an
`ANALYZER_VERSION` bump for a field the analyzer never needs to know about.

Limit: `interface.missing` reads `modules` alone, so a
`pkg.module:Name` entry whose module exists but whose name does not — a genuine typo in the name
half — still reads as `interface.unused`, the same blind spot `_entry_used` already carries for
the same reason. `planned` takes no part in an AD-20 inside's public-surface match, so a level's
own contract and its inside may name different planned facades without either check noticing;
only their `public` lists are held equal. Nothing stops an entry from naming both lists at once -
`public` then reports it `interface.missing` because it is not yet built, and `planned` reports
nothing because that is exactly what `planned` expects — so an architect who wants no finding
until a facade exists keeps the entry in `planned` alone. Check:
`tests/test_validation.py::test_missing_public_entry_is_a_diagnostic`,
`test_planned_entry_not_yet_built_has_no_diagnostic`,
`test_planned_entry_built_but_unused_is_target_work`,
`test_built_planned_entry_reached_by_import_needs_promotion`,
`test_unused_public_entry_is_a_diagnostic` reading a scanned module, and
`test_planned_entry_owned_by_another_component_is_a_diagnostic` with its underscore and namespace
twins; `tests/test_contract_model.py`'s corpus with `tests/contracts/valid/component-planned.json`
and `tests/contracts/invalid/component-planned-malformed.json`;
`fixtures/demo_catalog_validation.py`'s `validation-interface-missing`,
`validation-interface-planned-not-built` and `validation-interface-planned-built` rows, run by
`tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings`; and
`archkeel validate --root . --json` on Archkeel's own contract, which declares no `planned` entry.

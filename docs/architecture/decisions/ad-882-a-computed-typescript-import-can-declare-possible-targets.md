# AD-882: A computed TypeScript import can declare possible targets

**Status.** Accepted. Part of #723. Extends AD-664.

**Problem.** The TypeScript collector leaves a gap for `import(name)`. Unlike a Python loader,
the gap has no site that a contract can name. A registry with a known reach therefore cannot
state its scope for a dependency check.

**Decision.** Mark a computed runtime `import()` as a `loader` door. Name the site by its module
and line in `declarations.door_reach`. Keep the gap unless the declaration matches and applies.
The collector states no scope for this call. A scope selector needs a scope stated by the collector.
The contract gives an upper bound, not a list of modules that loaded. Its `loads` entries use
the same qualified module prefixes as other door declarations.

Use those possible edges in the existing boundary and cycle checks. The frame lists the
concrete scanned targets as `possible_loads` on the applied declaration. It retains `loads`
for the original prefixes, including any external prefixes. A declaration adds no collector
import fact and does not count in the observed topology or the component graph check.
A finding labels an edge supplied by the declaration as possible. An allowed edge permits PASS
only under the stated premise. An uncovered site or a missing project target does not permit PASS.

**Rejected.** Do not treat an arbitrary expression as a literal or infer a registry from
one caller. Do not add a second contract field for TypeScript.

**Limit.** This slice binds a premise to a module and line, not to a constant or code digest.
Review the declaration when the call changes, even if it remains on the same line. This slice
does not fold Python expressions or add declarations that follow constants. It does not declare
computed `require()` calls, type imports or unresolved literal paths.

**Tests.** `tests/test_cli_typescript_import_call.py` checks an allowed target, a forbidden
target, a second open site, a missing target and an unsupported scope selector through the product
entry.

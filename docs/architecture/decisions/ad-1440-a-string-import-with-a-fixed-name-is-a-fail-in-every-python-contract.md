# AD-1440: A string import with a fixed name is a FAIL in every Python contract

Status: accepted (owner decision 2026-11-28, board lesson 20; design `designs/STRING-IMPORT-FAIL.md`). Amends AD-472,
AD-536 and AD-1052.

## Why

`importlib.import_module("app.x")` and `__import__("app.x")` hide an edge that an import statement shows. The scan
proved them (AD-472) and drew the edge, but never judged the call. Brittle code is a FAIL. Dynamic code that the scan
cannot prove stays UNKNOWN.

## Decision

1. The Python collector states a construct `string_import`: one `typing_signals` record for each call that the proof of
   `literal.rs` accepts (the loader binding proved, one literal argument or the adjacent local string of AD-1026). The
   record holds the module (`owner`), the line and the literal target (`expression`). A lazy-table load (AD-560) computes
   its name from a table and is no site. The edge is unchanged.
2. A run whose collector states the construct holds the built-in rule `STRING-IMPORT`: a `forbidden_construct` of the
   scan namespace that the model adds to the root contract. It is not in the contract file, has no switch, and does not
   change the contract digest. A mount does not hold it. The other collectors state no such construct, so TypeScript,
   Dart and Rust have no rule and no site (`import("x")` and `require("x")` are the import of the language).
3. Each undeclared site is a violation: FAIL, exit 1, with the evidence of the call. A computed name, `eval`, `exec`, an
   alias and a stored loader are no fixed name: they are the existing gaps and hold the rule UNKNOWN as for any
   `forbidden_construct`. A found site is a FAIL in an incomplete scan too.
4. `declarations.string_imports` (contract 3.22.0): `{id, module, line, target, count?, rationale, provenance}`. A record
   applies to the sites of that module, line and target when the count (default 1) is their number. The rule then reads
   PASS under its premise: the run says "N declared string imports" and names `module:line`. A record with another target,
   line or count applies to nothing: the site stays a FAIL, and the hygiene row `string_imports.unmatched` names it. Only
   the root contract declares (`string_imports.inside`).
5. The id `STRING-IMPORT` is reserved: a contract rule with it is the hygiene defect `rule.reserved_id`.
6. A `find_spec` call with a literal stays a gap (UNKNOWN): it needs a flow proof that `exec_module` follows.

## Counter-examples (`tests/test_cli_string_import.py`)

- `import_module('app.service')`, `__import__('app.service')`, `__import__('datetime')`, the adjacent local string and a
  call in a function: each FAIL with one violation.
- A computed name, a concatenation, an f-string, a stored loader, `eval` and `exec`: no violation, the rule is UNKNOWN.
- No string import: PASS. A declared site: PASS under the premise. Another target, line or count: FAIL and a defect.
- Two calls on one line need `count: 2`.

## Not done

- A site that a hazard hides (a module with a computed loader) keeps the rule UNKNOWN until the hazard is declared.
- EE changes from UNKNOWN to FAIL for `__import__("datetime")` (two sites); the migration patch fixes them.

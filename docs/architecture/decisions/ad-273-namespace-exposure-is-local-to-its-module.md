# AD-273 A namespace exposure withholds loader proof in its own module only

**Decision.** This amends AD-240. Three classes replace the snapshot-wide rule:
- **No exposure:** a `globals()` that only reads names (`set(globals())`, `sorted(globals().keys())`,
  `'x' in globals()`, `len(...)`, iteration). Keys are strings and reach no shared object. The
  consumer must be the builtin: a module's own `def set` does not count. A keys view keeps its dict in
  `.mapping`, so `.keys()` passes the check on to the next consumer.
- **Own module only:** `eval`, `exec`, `__annotations__`, `get_type_hints` and
  `inspect.get_annotations`. They withhold the proof of both loaders in that module. The code that
  `eval` and `exec` run is not proved; AD-240 already does not prove arbitrary runtime effects.
- **Every module, both loaders:** everything else. `globals()` as a dict (`globals()['importlib']`,
  `.get`, `.items()`, a variable, an argument) holds references to shared objects such as
  `importlib`. `__builtins__`, `f_builtins`, `f_globals` and `f_locals` reach the shared builtins
  dict or a caller. A trigger that a later change adds fails closed into this class
  (`exposes_own_namespace_only` is the one list of the own-module names). Codex found four of
  these on #717.

Still global as before: a scanned module that is `importlib` or `builtins`, and a visible
mutation or escape of a loader (`importlib.import_module = ...`, `mutate(importlib)`), for the
loader it names.

**Reason.** `_loader_mutations` treated the exposure of any one module as a change of both loaders
for the whole snapshot. A namespace exposure changes the names of the exposing module. It does not
rebind `importlib.import_module` for another module. The loader escape is already a separate check.

Measured on DATAMIMIC EE (internal, 1,174 files, one pinned copy):
- 5 modules expose a namespace (`globals()` in 2, `eval` or `exec` in 3).
- Before: 8 loader calls in 7 files, all unproven. 34 of 431 rules read UNKNOWN.
- After: 406 PASS and 25 UNKNOWN. The 25 come from 4 loader calls with a variable target
  (two registries in `domains`, two in `engine`). Exit code 0 before and after.
- 4.0.1 read PASS for all 431, because it had no dynamic-dependency record.

**Not changed.** A route to a foreign namespace that no scan found before (`sys.modules[...]`,
`vars(module)`, `setattr(module, ...)`) is still not found. A target that is not a literal stays UNKNOWN. Code that `exec` runs can still
change a loader at runtime; AD-240 already does not prove arbitrary runtime effects. A project
cannot yet accept a loader call with a variable target; that needs its own decision.

**Rejected.**
- Ignore `eval` and `exec` for loaders everywhere: the exposing module itself must stay unproven.
- Treat a read-only `globals()` as safe: it needs the use of the result, and is not needed to reach
  25 on EE.
- Keep the global rule and document it: one `eval` in one file then hides every dynamic proof.

**Check.**
- `tests/test_loader_exposure_scope.py`: 11 own-module forms, 7 names-only forms and 3 loader forms.
  An own-module form in another module leaves the proof (FAIL witnessed) and in the loading module
  gives UNKNOWN. A names-only form changes no loader anywhere. 28 uses of `globals()` are classified
  one by one, and 19 escapes (loader mutations, `__builtins__`, frames, `globals()` as a dict) withhold
  proof in every module.
- Direct tests: a scanned `importlib` or `builtins` module is global; an own-module exposure is
  listed by name; an unlisted trigger is not own.
- 31 faults in the classification are all caught: the old rule, exposure ignored or global, escapes
  local, owner not global, everything or nothing own, each of the 7 own names, and 17 changes to
  the names-only rule (each branch, each of the 6 containers, the callee skip).
- The existing 118 dynamic-dependency tests pass.

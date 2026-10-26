# AD-273 A namespace exposure withholds loader proof in its own module only

**Decision.** This amends AD-240. A module that calls `globals()`, `eval` or `exec` no longer withholds the proof of `importlib.import_module` and `__import__` in
every module of the snapshot. It withholds the proof in that module only. These stay global:
- a scanned module that is `importlib` or `builtins` itself;
- a visible mutation or escape of a loader (`importlib.import_module = ...`, `mutate(importlib)`,
  an alias that mutates), for the loader it names.
- any use of `__builtins__`, for `__import__`: every module shares the builtins dict, so
  `__builtins__["__import__"] = f` changes the loader for all of them (Codex found it on #717).

**Reason.** `_loader_mutations` treated the exposure of any one module as a change of both loaders
for the whole snapshot. A namespace exposure changes the names of the exposing module. It does not
rebind `importlib.import_module` for another module. The loader escape is already a separate check.

Measured on DATAMIMIC EE (internal, 1,174 files, one pinned copy):
- 5 modules expose a namespace (`globals()` in 2, `eval` or `exec` in 3).
- Before: 8 loader calls in 7 files, all unproven. 34 of 431 rules read UNKNOWN.
- After: 406 PASS and 25 UNKNOWN. The 25 come from 4 loader calls with a variable target
  (two registries in `domains`, two in `engine`). Exit code 0 before and after.
- 4.0.1 read PASS for all 431, because it had no dynamic-dependency record.

**Not changed.** A target that is not a literal stays UNKNOWN. Code that `exec` runs can still
change a loader at runtime; AD-240 already does not prove arbitrary runtime effects. A project
cannot yet accept a loader call with a variable target; that needs its own decision.

**Rejected.**
- Ignore `eval` and `exec` for loaders everywhere: the exposing module itself must stay unproven.
- Treat a read-only `globals()` as safe: it needs the use of the result, and is not needed to reach
  25 on EE.
- Keep the global rule and document it: one `eval` in one file then hides every dynamic proof.

**Check.**
- `tests/test_loader_exposure_scope.py` crosses 5 exposure forms with 3 loader forms: an exposure
  in another module leaves the proof (FAIL witnessed), the same exposure in the loading module gives
  UNKNOWN, and 7 visible mutations withhold proof of their own loader only.
- Direct tests: a scanned `importlib` or `builtins` module changes both loaders everywhere; an
  exposing module is listed by name and changes nothing globally.
- 6 faults in `_loader_mutations` (the old rule, exposure ignored, exposure global, escapes local,
  owner not global, `__builtins__` not global) are all caught. The existing 118 dynamic-dependency tests pass.

# AD-206 Check families keep existing behavior

Issue #357: diagnostic families live in separate validation modules; `run_validate`
keeps its entry point and existing imports remain available. Function bodies are unchanged.
No registry, new interface or policy widening. The boundary-type move follows the same rule.

Checks: native validation and boundary fixtures, fresh self-validation and `make against`.

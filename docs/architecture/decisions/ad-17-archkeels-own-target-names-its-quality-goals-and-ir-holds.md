# AD-17 Archkeel's own target names its quality goals, and `ir` holds pure derivations

The architect confirmed these goals: deterministic, stable `ir` and `check`;
an isolated analyzer behind its digest; replaceable `render` and `host`; a thin
`cli` composition root. Component responsibilities and dependency reasons record them.

`ir` owns shared evidence models, codecs and pure derivations needed by multiple
components, such as interface edges and open decisions. Derivations perform no I/O
and import only `ir`.

Remove placeholder `accept` until implemented, leaving six components and 30
ordered pairs. After 0.3.0, split `ir/codec.py` at its contract, observation, delta,
result and lock seams as a separate public-IR decision.

At `7b2502a`, `accept` always exited 2 but required 12 pair decisions, `ir` contained
undeclared derivation responsibilities, and the 1,278-line codec had five responsibilities.
Check: no `accept` component, explicit quality goals, clean self `validate` and
`report`, and six components in D-self.

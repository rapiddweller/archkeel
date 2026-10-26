# AD-269 Skip one too-deep Python module with a coverage gap

**Decision.** The Python collector measures the AST depth of each module right after the
parse. A module deeper than `MAX_AST_DEPTH` (5,000 levels) is not analyzed. It becomes one
coverage gap with the file and the reason, and the scan goes on. A `RecursionError` or a
`MemoryError` from `ast.parse` itself gets the same treatment, because CPython raises
`MemoryError` when its parser stack overflows. `RECURSION_LIMIT` (20,000) moves to
`source.py`, so the limit and the ceiling sit side by side.

**Reason.** The walkers are recursive. They use about three frames for each AST level. With
the limit of 20,000 frames (AD for #676), a chain of 6,500 operators passes and 7,500
fails. One generated file with a huge sum then stopped the whole scan with a
`RecursionError`. The same happens for long attribute chains and long call chains. A
conditional chain fails earlier, in the parser. A gap for one file is the same outcome as
a syntax error in that file. The rest of the project stays observed.

**Rejected.**
- Catch `RecursionError` around the walkers: a walker can fail in the middle of a pass
  and leave partial records. Checking before the analysis keeps each module all-or-nothing.
- Raise the recursion limit again: a higher limit moves the ceiling and risks a stack
  crash. A file with an unbounded chain still fails.
- Rewrite the walkers as iterative: this is the real cure, but it touches every visitor.
  It has no evidence of need beyond generated files.

**Check.**
- `tests/test_language_collectors.py`: a module nested `MAX_AST_DEPTH + 1,000` levels
  (sum, attribute chain, conditional chain) gives exit 0, one gap that names the file, and
  all other files parsed.
- The existing deep-sum test (2,000 operators) still collects the module.

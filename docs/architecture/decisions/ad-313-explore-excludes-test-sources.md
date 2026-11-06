# AD-313 Explore excludes recognized test sources

**Decision.** Default Python and TypeScript `explore` excludes files recognized by their test
naming and directory conventions. The collection request carries this scope in protocol 9;
protocols 1 through 8 keep their existing shape. Dart and other collection callers keep their
current behavior. Explicit governance scopes keep their current behavior.

An import from selected production source into an excluded test source is UNKNOWN. It is not a
complete observation of that import. Test names are classified by exact conventions; names such as
`latest.py` and `latest.ts` remain production candidates.

**Reason.** Implementation Explore should describe implementation code. Treating known tests as
implementation changes ownership and can hide the production structure.

**Limit.** Dart test exclusion is not implemented. The collector does not yet report counts and
reasons for intentionally excluded files. Unrecognized test naming remains in scope. This decision
does not close issue #874 until Explore and Studio expose the applied exclusions and their limits.
Programmatic Explore with a V1–V8 external collector fails at the V9 protocol boundary. CLI Explore
has no external collector override.

**Check.** Python and TypeScript source-root fixtures cover test exclusions, production named
`latest`, and production imports across the excluded boundary. The public demo catalog includes
`explore-excludes-test-sources`, with `shop/tests/test_latest.py` inside the selected root.
Protocol tests preserve V8 and round-trip the V9 scope. The issue remains open for exclusion
reporting and Studio coverage.

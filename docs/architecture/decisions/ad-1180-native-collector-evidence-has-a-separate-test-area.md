# AD-1180: Native collector evidence has a separate test area

Full verification run 45838109119 spent 25.1 minutes in native collector tests.
The job budget is 15 minutes. Several files account for most test time.

Rust collector tests, site scaling and the collector catalog run in a separate
area. The catalog gives that area a nonempty PR selection. Both areas keep the
same test tiers and the main core cache. Native changes select both areas.

We did not move tests to a later tier or raise a timeout. The new impl oracle
exceeds the budget in CI and fails an assertion; issue #2124 tracks that failure.

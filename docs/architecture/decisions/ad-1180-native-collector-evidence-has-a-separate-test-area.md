# AD-1180: Native collector evidence has a separate test area

Full verification run 45838109119 spent 25.1 minutes in native collector tests.
The job budget is 15 minutes. Several files account for most test time.

Rust collector tests and the collector catalog run in a separate area. The
catalog gives that area a nonempty PR selection. Both areas keep the same test
tiers and the main core cache. Native changes select both areas.

We did not move tests to a later tier or raise a timeout. The new impl oracle
also runs in the new area during Full. Its time in CI is not yet known.

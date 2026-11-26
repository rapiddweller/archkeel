# AD-1114 Native collector tests reuse the gate core cache

**Status.** Accepted. Amends AD-732 and AD-754.

**Decision.** The native collector test job restores the gate core for its native tree.
On a core cache miss, it restores the existing Rust build cache and builds the current tree.
The existing tree stamp decides whether the core can be reused. All selected tests still run.

**Reason.** The collector job built the same core on each runner.
In run 44330175254, the cold build took 2 minutes 17 seconds.
The job reached the 15-minute limit while its tests still ran.

**Limit.** A cold cache still requires a build. The tests can still exceed the job time limit.
The cache does not reduce the test execution time.

**Tests.** `tests/test_core_cache.py` checks the cache paths, tree hash and build-on-miss contract.

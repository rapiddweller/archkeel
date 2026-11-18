# AD-902 A cache marker does not bound Cargo configuration

**Status.** Accepted for #1859. Amends AD-774.

**Reason.** Cargo reads configuration from its working directory and the directories above it.
A valid cache tag does not change that search. A registry override below a tag can therefore
leave a rule with a PASS that has no proof of registry identity.

**Decision.** Inspect Cargo configuration below cache markers. Keep the existing snapshot and
outside-settings boundary. Do not infer a build start directory from a manifest or a directory
name. A directory alias adds no uncertainty when the same walk checks its real directory.
A `.cargo` link, an alias outside the walk, or an incomplete walk withholds registry identity.
Cache markers still affect the separate source walk and work survey.

**Limit.** The Cargo walk keeps its depth limit of 128 and entry budget of one million.
A snapshot listing stops on the first entry above one million and returns no partial list.
The walk lists build output but does not read its ordinary files. Keep large
build caches outside the scan snapshot when possible. A scan that cannot inspect a cache must not
claim that the cache has no relevant configuration.

**Rejected.** Validate the cache tag signature and then skip its tree. The signature identifies
a cache convention, not the Cargo configuration that applies. Skip any directory named `target`.
Cargo can start inside it, and an ordinary directory can have that name.

**Tests.** The registry tests compare configurations with absent, invalid and valid cache tags.
They also cover directory aliases, an external link and an unreadable directory.
The snapshot test rejects an over-limit listing. The Core test checks the rule and the premise
for a nested `paths` override.

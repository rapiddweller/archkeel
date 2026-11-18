# AD-929 Dart survey results need no runtime derives

**Decision.** Remove unused traits from `PartOwner` and `Survey`. Store the part path
and the two module identities. Do not copy the owning library's path into `PartOwner`:
the reply uses its module identity.

**Reason.** Only a test formats `Survey`, and it can print the coverage it checks.
No caller clones or compares a `PartOwner`. These traits in the survey root gave its
helpers a possible return path through that root.

**Rejected.** Exempt derived traits from the cycle rule. The rule must still account
for traits that a caller can execute.

**Limit.** The change does not affect Dart records, scope or the cycle proof. Other
module cycles still have possible return paths.

**Tests.** The Dart survey tests check the part path and its owning module. The
native self-scan measures the pairs that the module rule still reads.

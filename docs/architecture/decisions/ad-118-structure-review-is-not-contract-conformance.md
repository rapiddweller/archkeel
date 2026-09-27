# AD-118 Structure review is not contract conformance

Green top-level rules did not expose the CE experiment's overloaded interiors (#172).
The shipped skill therefore reviews maintained physical packages recursively within the
agreed scope, including folders without a contract.

More than seven direct children triggers a cohesion review, not a checker failure or an
automatic split. Smaller mixed-responsibility packages need review too. Keep justified
larger groups; do not create arbitrary buckets, wrapper packages or diagram-only boundaries.

Explicit `inside` contracts govern deliberate boundaries. They do not replace physical
review, and folders do not implicitly become contracts. Record reviewed and deferred areas,
exceptions, uncertain decisions and enforcement limits. Assessment does not authorize edits.

This is agent guidance, not a deterministic guarantee of design quality. Installer tests
check distribution; independent scenario review checks the guidance's interpretation.

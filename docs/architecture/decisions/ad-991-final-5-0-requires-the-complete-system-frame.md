# AD-991: Final 5.0 requires the complete system frame

Status: accepted. This decision applies only to the final 5.0.0 release tag.

## Decision

Before publication, install the candidate host wheel in an isolated environment.
Run its core against the system contract at the release commit.
Read the rule decisions in the bound system frame.
Each declared part must contain exactly the rules of its contract.
Each rule must have its declared kind and a PASS decision.
Reject a missing, repeated, foreign or undecided rule.
Reject a different commit, contract digest or core binary.
Print the premises that qualify the decisions.

The normal self-check and the rolling main-build wheel keep their present behavior.
They show UNKNOWN and do not require every rule to pass.
The fixture smoke test does not prove the system verdict.
The exit code and badge do not prove the complete set of rule decisions.

## Limits

The release check rejects a system rule or an inside contract.
Neither occurs in this system today. Extend the identity check before adding either.
Before the final release, compare FastAPI and bazel_worker with 4.0.1.
These comparisons are separate from the system check.

`tests/test_cli_release_system.py` checks the rule set, decisions and identity failures.

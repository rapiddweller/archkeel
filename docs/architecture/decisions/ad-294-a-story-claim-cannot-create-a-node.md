# AD-294 A story claim cannot create a node

**Status.** Accepted. Issue #830; amends AD-291 item 4.

**Decision.** In a story spec, a step marked `claim: true` may assert a transition between nodes
that exist in the snapshot; the check does not look for a call. The claim does not make an endpoint
exist: an invented node remains `missing` (or `unknown` when source coverage is incomplete), and its
transition cannot pass as `claim`. View-edge claims and claims in non-story specs retain their
existing meaning. An external system remains an author claim only through the existing explicit
`external` field.

**Reason.** A claim can bridge an unobserved relationship, but cannot add source evidence.

**Rejected.** Trusting arbitrary endpoint names because the relation is marked as a claim.

**Checks.** `tests/test_cli_story.py` checks a claim between real nodes and a negative control with
an invented node.

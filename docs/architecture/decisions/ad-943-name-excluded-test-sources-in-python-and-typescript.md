# AD-943 Name excluded test sources in Python and TypeScript

**Decision.** Python and TypeScript include recognized test paths removed from a linked scan in
the existing `excluded_sources` result. The TypeScript private worker transfers the same list.
The default of `validate` and `report` remains tests included. A project must opt in to exclusion.

**Reason.** A verdict for a test-free scope must not hide which paths the scan left out.
Changing the default of governance commands can hide forbidden test dependencies.
The unavailable `explore` command is a separate product scope, not a reason to change governance.

**Alternatives.** A global default exclusion weakens existing checks. A second file walk in the
shell can disagree with the collector. Both are rejected.

**Limit.** Conventions can identify a production file as a test. The list is not proof of its
purpose. The Python list covers discovered regular paths; unreadable or dangling entries and
linked directories are not an exhaustive inventory. The TypeScript list covers the collector's
selected and project-source walks. The public collector stream does not carry the list. Studio
and Explore are not available on main. This decision does not close issue #874.

**Check.** The Python and TypeScript linked-reply tests name excluded paths and keep `latest`.
The TypeScript private-worker test checks the transferred list. CLI tests check explicit scope,
the JSON and text views, a forbidden dependency and a production import into an excluded test.

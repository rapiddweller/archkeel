# AD-297 An incomplete call list is explained as unavailable

**Status.** Accepted. Issue #830; builds on AD-60 and AD-100.

**Decision.** With `report --only calls`, an incomplete source observation keeps
`filtered_calls: null`. The terminal and HTML summary say the call list is unavailable and that no
call count is claimed. A null remains distinct from a measured empty list.

**Reason.** A partial scan cannot report a complete call list or claim that no calls were found.

**Rejected.** Filling the list from partial evidence or presenting null as zero.

**Checks.** `tests/test_unresolved_call_sites.py`.

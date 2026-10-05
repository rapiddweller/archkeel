# AD-185 Provider use survives initializer ownership

Exact initializer ownership must preserve a provider's proven use through an
ancestor-published re-export (#338). Rule evaluation and lifecycle validation
share chain coverage; ancestor publication and unique ownership remain required.

Lifecycle records stay inside their own contract mount. Unproven candidates
retain UNKNOWN and never become proven use. Private or unpublished routes
cannot satisfy the provider interface.

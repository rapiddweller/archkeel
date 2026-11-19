# AD-1001: Read the default function kind before the pattern check

## Status

Accepted. Keeps the behavior of AD-1000.

## Decision

Read the node kind before `matches!` in `anonymous_default`. Keep the name
and body checks after the kind check. Their evaluation stays conditional.

## Reason

The Rust collector reads the typed `Cx` receiver in ordinary code. Inside
`matches!`, it records the method name without the receiver. The separate
open site holds the interface rule even though the collector knows the import.
Moving this call does not change when it runs. We do not exempt macro calls
from the interface rule.

## Checks

The native self-check requires the same `Cx` route and no open site for this
pair. The UML controls still accept a listed anonymous default function and
report a finding for an unlisted one.

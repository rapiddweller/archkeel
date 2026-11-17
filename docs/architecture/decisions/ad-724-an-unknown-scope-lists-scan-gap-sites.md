# AD-724: An unknown scope lists scan gap sites

## Status

Accepted for the report.

## Decision

When a rule is held by scoped gaps, the UNKNOWN section lists up to 100 scan gap sites with
their reasons and states the count. It says that not every scan gap holds every rule: the
collection gaps in the frame do not carry the identifiers that connect them to individual
rule holds. Sites without a location are not listed.

The page suggests checking whether a door accepts declared reach. A PASS under such a
declaration is conditional, and not every gap can be declared.

## Checks

`html_unknown.rs` tests sites, conditional advice, escaping and a scan with no sites.

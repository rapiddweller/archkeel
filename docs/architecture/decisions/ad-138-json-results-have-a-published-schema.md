# AD-138: JSON results have a published schema

Publish a result schema for check, validate and report, reusing IR schemas.
Exit codes cannot substitute for verdicts; unmeasured totals are null, distinct
from measured zero. Legacy integer-total lock and delta formats remain readable.

Pin schema and producer together. Meaning, type, nullability and enum changes are
breaking; optional ignored fields are additive. Shape proves neither
authenticity nor conformance. Other commands and canonical artifacts keep separate
contracts.

[Published schema](../../../schema/command-result.schema.json) and
[consumer proof](../../../tests/test_result_schema.py).

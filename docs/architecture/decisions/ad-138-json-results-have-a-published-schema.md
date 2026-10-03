# AD-138: JSON results have a published schema

## Problem

Agents consume `codec.result_payload` without a published shape. They can mistake an
unmeasured null for an empty list, or a report's exit 0 for PASS.

## Decision

Publish `schema/command-result.schema.json` for check, validate and report.
Reuse the common IR evidence, decoded observation and contract rule schemas.
Describe each mode's nullability, verdicts and structured evidence; require diagnostics at exit 2.
Package the asset through the existing schema directory inclusion.

The schema `$id` owns its version. Pin it with the producer CLI. Optional ignored properties
are additive; field removals, new requirements, type/meaning/nullability changes and enum
extensions are breaking. Details live once in `docs/reference.md`.

Result schema and accepted lock 2.0.0 correct unmeasured call totals to null (#122, #276).
The pending profile-aware Delta 1.4.0 carries the same field. Published older lock/delta
versions retain integer totals; their zero/null sentinel remains readable. Measured zero
and independent count/share guards keep their meaning (AD-97, AD-136).

## Rejected

- A second result model or runtime validator duplicates the typed producer and adds cost.
- A new output version field changes the wire before a consumer needs it.
- Treating exit codes as verdicts loses report FAIL and UNKNOWN results.

## Limit

This checks shape, not source authenticity, arithmetic or contract conformance. Argument
parser, init and skill results, and canonical architecture artifacts have other contracts.
Release follows the CE migration; this change does not publish a release.

## Checks

`tests/test_result_schema.py` validates real CLI demos and rejects missing/malformed verdicts,
diagnostics and source evidence. A small consumer preserves FAIL and UNKNOWN. Installed wheel
and sdist smoke tests read the schema and its references without a source checkout.

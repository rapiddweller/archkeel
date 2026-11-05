# AD-224 Configurable finite collector output limit

Valid SourceFacts for a large configured scope can exceed the process port's
64 MiB stdout ceiling before Core evaluates policy (#489). The public collector
already supports a finite limit; CLI composition must expose it rather than
silently narrow the scan or remove source facts.

An optional positive integer `scan.collector_output_limit_bytes` overrides the
collector stdout limit for report, validate and historical check. Absent means
the existing process-port default. The parser rejects booleans, non-integers,
zero and negatives. All entry points also enforce the active interpreter's
`sys.maxsize // 16`, so the decompressed-size bound remains representable. The
schema's static maximum is the equivalent 64-bit ceiling; runtime validation
remains authoritative on any narrower platform. The package does not declare a
32-bit support guarantee.
`init --collector-output-limit-bytes` uses and persists the chosen limit, so a
large project can initialize without an existing configuration.

The CLI injects the limit; Core retains source-only requests and policy ownership.
No source facts, roots, protocol validation, stderr bound or timeout are removed.
Historical check reads accepted Git configuration and rejects candidate changes
to it; a command-line override cannot bypass that binding.

Rejected: raise the default for every project, allow unlimited output, truncate
facts, or omit roots to fit the transport. Larger explicitly chosen limits can
increase memory use; they establish no additional evidence or architecture grant.

Proof: tests/test_collector_output_limit.py covers parser/schema, every language's
default, initialization failure without writes, persisted limits and complete
report/validate scope after raising a too-small ceiling.
tests/test_configured_collector_check.py proves historical check uses the bound
limit and rejects incomplete accepted evidence before collecting the candidate.

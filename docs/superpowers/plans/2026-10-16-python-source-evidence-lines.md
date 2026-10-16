# Issue 542: Python source evidence uses Python physical lines

## Problem and scope

The Python AST counts LF, CRLF and CR as physical source newlines. str.splitlines also treats Unicode line/paragraph separators inside a valid Python string literal as boundaries. parse_sources currently passes that broader list to the evidence owner; AST lineno can then cite blank or wrong nonempty text. This caused native TypeScript Collector comparison mutations to lose a complete source trace. Core's trace refusal is correct and must remain unchanged.

Change only the parsed module's line view: normalize CRLF/CR to LF, then split LF. Keep original source text, raw bytes, source digest, node positions and all native policy/trace checks unchanged. No literal escaping, negative-test removal or observation exception.

## Verification sequence

1. Commit this plan before code.
2. Native RED regression covers real U+2028/U+2029 in literal data, LF/CRLF/CR, absent EOF newline, direct and Final-alias comparisons. It checks the actual evidence file/line/excerpt, rule FAIL and complete rule/fact/source traces. A raw-input check pins source text, bytes and the digest independently.
3. Apply the single owner-local view normalization; rerun native regression and the original four Collector mutations with the final c0 observer and Source-Wire carrier.
4. Run relevant existing Python/source-evidence checks, lint/mypy, hygiene and native unchanged baseline. Prepare separate PR for final independent Astra review. Union the one-line source.py delta with concurrent Binding enum changes rather than copying whole files.

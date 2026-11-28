# AD-1420: The self-scan result is reused for the same inputs

Status: accepted. Builds on AD-1380 (one system scan) and AD-1260 (the gate judges one run).

## Why

The self-scan costs 6 to 8 minutes of the PR gate. A pull request that changes only docs, tests or
workflows gives the scan the same inputs as main, so it gives the same result.

## Decision

1. `tools/self_scan_cache.py` keys a saved result of the system scan by a hash of its inputs. It is a
   result cache. It is not a comparison and it is not a gate.
2. Every file of the repository counts, by content, except the formats of `NEUTRAL_SUFFIXES` (`.md` and
   images). This includes a file not yet added to git, a link with the content of its target, and an
   ignored file that a collector can read. Build output folders count only through a `.cargo` folder in them. A `.env.*` file counts whatever its last suffix.
   A list of what the collectors read failed in review again and again (outside scripts, native
   extensions, walk markers, preload configurations), so the rule is the opposite. The entry also holds
   the neutral documents that the scan read: the files that the core bound (`contract_files`) and every
   path that a contract cites, also an absent path.
3. Main saves the result after the gate is green. The tool refuses a result that does not show its
   inputs covered: a scanned file outside the static inputs, a part whose configuration is not static,
   a refusal, or a result without rules.
4. A pull request restores the entry of main. `make self-validate-system` reuses it when the static
   key and every saved document match, and then `tools/self_check_gate.py` judges it as it judges a
   fresh result. Any other case, and any error, runs the scan as before: the cache fails closed.

## Measured

A change of `docs/roadmap.md`, `README.md`, a test, a fixture, `.github/AGENTS.md` and
`CONTRIBUTING.md` gave a system result that differs from main only in the snapshot `git_head`. The
reused result keeps the `git_head` of main.

## Not done yet

- A pull request that changes a `.md` or an image file that a collector reads without a contract citing
  it would give a stale result. No collector reads such a file as a source today.
- A change of a test or a workflow file misses and scans: the hit rate is highest for docs-only changes.

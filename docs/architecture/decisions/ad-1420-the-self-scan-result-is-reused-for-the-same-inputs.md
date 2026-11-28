# AD-1420: The self-scan result is reused for the same inputs

Status: accepted. Builds on AD-1380 (one system scan) and AD-1260 (the gate judges one run).

## Why

The self-scan costs 6 to 8 minutes of the PR gate. A pull request that changes only docs, tests or
workflows gives the scan the same inputs as main, so it gives the same result.

## Decision

1. `tools/self_scan_cache.py` keys a saved result of the system scan by a hash of its inputs. It is a
   result cache. It is not a comparison and it is not a gate.
2. Static inputs, hashed by content: `native/`, `src/`, `studio/`, `schema/`, `tools/rustc-facts/`,
   `.archkeel/`, every `archkeel.toml`, every `*contract*.json`, every `rust-toolchain*`, every
   `.cargo` file, every link, `pyproject.toml`, `uv.lock`, `Makefile`, the system document and the
   shell configuration. The key also holds the documents that the scan read: the files that the core
   bound (`contract_files`) and every path that a contract cites, also a path that is absent.
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

- A pull request that changes a file that no contract binds but that the core reads in another way
  would give a stale result. The counter-example tests name the known classes.

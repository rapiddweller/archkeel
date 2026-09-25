# AD-104 A contract the compared revision lacks is introduced

`validate --against <ref>` reads the configured contract at `<ref>` (AD-61). When `<ref>`'s tree
holds nothing at that path, the run no longer stops with `against.invalid`. It reports one
widening, `contract introduced: <path> does not exist at <ref>`, which fails with exit 1 unless
an amendment binds it. `--write-amendment` records it with `before_digest` set to the SHA-256 of
no bytes, which no canonical contract can have, so the record binds "no contract" to this exact
one (#150).

Only a missing blob, `check/git.py`'s `MissingBlobError`, is an introduction. A revision Git
cannot resolve, a tree, symlink or submodule at the path, or a contract that does not parse stays
`against.invalid`, exit 2. A baseline missing at `<ref>` still means no prior known debt when the
contract exists there; a baseline Git holds but cannot hand over is now `against.invalid` too,
where it used to read as no debt. With the contract introduced, nothing else at `<ref>` is
compared: every baseline entry and budget value belongs to the one introduction, and no second
scan names call sites (AD-100) under a contract `<ref>` does not have. The configuration file is
never read at `<ref>`; the contract path comes from today's file, so a `--config` or `--root`
scope that arrives with its configuration is one introduction as well.

`read_blob` finds a `--root` below the repository's top level with `git rev-parse --show-prefix`
and looks the path up from the top, so every message names the blob Git was asked for.

Measured with the shop sample committed on `main` and the G-dart package added under `mobile/`:

| `validate --root mobile` | `main` | this change |
|---|---|---|
| `--against main` | exit 2, `against.invalid`: `missing regular Git blob: architecture-contract.json` | exit 1: `contract introduced: mobile/architecture-contract.json does not exist at main` |
| `--write-amendment`, then `--amendment` | exit 2, exit 2 | exit 0, exit 0 |
| `--against no-such-ref` | exit 2, `against.invalid` | unchanged |
| `--root .` (the shop), `--against main` | exit 0 | unchanged |

## Why a widening, not a skip

A missing contract is also what a moved one looks like: `contract` names a new path and the old
rules leave the comparison. A pass, or a skip with its own exit code, would let that change widen
everything unreviewed. An introduction asks the architect once, and the record says who decided.
CI no longer needs `git cat-file -e "$base:$dir/architecture-contract.json" || continue` to let a
new scope's first merge request through.

## Rejected

- A skip with its own exit code: every CI maps one more code, and a moved contract passes it.
- Comparing with an empty contract: every component and rule becomes its own finding, and a
  baseline that arrives with the contract adds one per entry. One finding says the same.
- Treating every `GitError` as absent: an unreadable revision would read as a new contract.
- Reading the configuration at `<ref>` to find an old contract path: it guesses that two files
  are one, and says nothing when the configuration is new too.

## Limits

- A moved contract is an introduction, not a rename. Like every amendment (AD-61), its record
  covers every finding of the change, here the whole contract and the baseline beside it; the
  diff shows both as added files.
- `read_blob` starts one more Git process per blob.

## Tests

`tests/test_against_introduction.py`: the second scope, the amendment and its binding, a moved
contract, a configuration `<ref>` lacks, a baseline introduced with its contract, a tree at the
contract or baseline path, and a baseline `<ref>` lacks. `tests/test_architecture_demo.py` runs
the `against-contract-introduced` rows of `docs/architecture-demo.md` with `--root mobile`.

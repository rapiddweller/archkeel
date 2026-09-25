# AD-104 A contract the compared revision lacks is introduced

`validate --against <ref>` reads the configured contract at `<ref>` (AD-61). When `<ref>`'s tree
holds nothing at that path, the run no longer stops with `against.invalid`. It reports one
widening, `contract introduced: <path> does not exist at <ref>`, which fails with exit 1 unless
an amendment binds it (#150). `--write-amendment` records `before_digest` as
`ir.codec.absent_contract_digest(path)`, the SHA-256 of a NUL, `no contract at ` and the
contract's repository path. A canonical contract is a JSON object, so no contract digest equals
it, and a record for one path cannot verify the same contract moved to another.

Only a missing blob, `check/git.py`'s `MissingBlobError`, is an introduction. A revision Git
cannot resolve, a tree, symlink or submodule at the path, or a contract that does not parse stays
`against.invalid`, exit 2. A baseline missing at `<ref>` still means no prior known debt when the
contract exists there; a baseline Git holds but cannot hand over is now `against.invalid` too,
where it used to read as no debt. With the contract introduced, a baseline `<ref>` still holds is
compared as before, so a moved contract cannot hide a padded baseline; a baseline `<ref>` lacks
too is not compared, since every entry would repeat the introduction. No second scan names call
sites (AD-100) under a contract `<ref>` does not have. The configuration is never read at
`<ref>`; the contract path comes from today's file, so a `--config` or `--root` scope that
arrives with its configuration is one introduction as well.

`read_blob` looks a path up as before, relative to `--root`. A missing or non-regular blob's
message names its path from the top level, found with `git rev-parse --show-prefix`.

Measured with the shop sample committed on `main` and the G-dart package added under `mobile/`:

| `validate --root mobile` | `main` | this change |
|---|---|---|
| `--against main` | exit 2, `against.invalid`: `missing regular Git blob: architecture-contract.json` | exit 1: `contract introduced: mobile/architecture-contract.json does not exist at main` |
| `--write-amendment`, then `--amendment` | exit 2, exit 2 | exit 0, exit 0 |
| that record, after `main` narrows the contract and the change moves the old one to `policy/contract.json` | exit 2 | exit 1: `contract introduced: mobile/policy/contract.json ...` |
| `--against no-such-ref` | exit 2, `against.invalid` | unchanged |

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
- One digest for every introduction, the SHA-256 of no bytes: an old record then verifies the
  same contract moved to any path `<ref>` lacks, after `<ref>` narrowed it.
- Treating every `GitError` as absent: an unreadable revision would read as a new contract.
- Reading the configuration at `<ref>` to find an old contract path: it guesses that two files
  are one, and says nothing when the configuration is new too.

## Limits

- A moved contract is an introduction, not a rename: its old rules are not compared, and the
  architect's record covers the whole contract. A baseline at the same path is compared.
- A record verifies the same contract introduced at the same path again, for example after
  `<ref>` deleted it: that is the decision the record states.
- A contract or baseline that does not parse at `<ref>` is reported without its path.

## Tests

`tests/test_against_introduction.py`: the second scope, the amendment and its binding, a record
replayed for a moved contract, a moved contract with a padded baseline, a configuration `<ref>`
lacks, a baseline introduced with its contract, a tree at the contract or baseline path, a scope
directory named `:app` or not UTF-8, and a baseline `<ref>` lacks. `tests/test_architecture_demo.py`
runs the `against-contract-introduced` rows of `docs/architecture-demo.md` with `--root mobile`.

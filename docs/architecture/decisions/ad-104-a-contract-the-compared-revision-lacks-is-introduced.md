# AD-104 A contract the compared revision lacks is introduced

A contract absent at `--against <ref>` is one widening, `contract introduced:
<path> does not exist at <ref>`, exiting 1 until amended (#150). The amendment
uses `absent_contract_digest(path)`: SHA-256 over NUL, `no contract at ` and the
repository path. It cannot equal canonical JSON-contract bytes or approve another
path's introduction.

Only `MissingBlobError` means absence. Unresolvable revisions, trees, symlinks,
submodules and malformed contracts remain `against.invalid`, exit 2. Missing
baselines mean no prior debt; unreadable existing blobs now fail instead of being
mistaken for absence. For introduced contracts, compare a surviving old baseline;
skip a jointly absent baseline to avoid duplicating the introduction finding.
No ref scan names calls (AD-100) without a ref contract.

Use today's configuration for the contract path; do not guess an old path from
ref config. Git blob errors name repository-relative paths via `show-prefix`.

Original shop/mobile experiment: absent contracts changed from exit 2 to exit 1;
writing and using an amendment exited 0. Moving the same contract under `policy/`
invalidated the old approval. An unknown ref still exited 2.

## Why a widening, not a skip

Moving policy looks like introduction and removes old rules from comparison.
A skip could silently approve that whole target. One path-bound finding requires
an explicit architect decision and removes CI's missing-contract skip.

## Rejected

Extra skip codes hide moved policy. Empty-contract comparison produces one finding
per entity instead of one introduction. A shared absent digest permits replay at
another path. Treating every Git error as absence hides unreadable revisions;
reading old configuration would guess file identity.

## Limits

A move is introduction, not rename; approval covers the whole contract, while a
same-path old baseline is compared. The same approval can cover reintroduction
at the same path. Ref parse errors still omit the contract/baseline path.

## Tests

`tests/test_against_introduction.py` covers scopes, exact/replayed amendments,
padded/simultaneously introduced debt, missing config, invalid Git objects,
unusual scope names and absent baselines. Introduction demos use `--root mobile`.

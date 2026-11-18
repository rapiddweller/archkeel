# AD-829: Main build publishes only a verified draft

Superseded by [AD-863](ad-863-the-main-build-release-is-replaced-by-verified-staging-and-rename.md).

## Decision

Create the first main build as a draft. Publish it only after every uploaded asset matches its SHA-256.
Refuse to replace an existing main build, including a draft.

## Reason

A failed upload must not expose an incomplete build or replace an existing build.
The release API cannot atomically replace all assets of a public release.

## Alternative

Upload directly to the public release. An upload failure can leave a partial set.

## Limit

Later main builds need a safe replacement design. A failed draft needs manual investigation.

## Check

`tests/test_main_build.py` checks the draft, the asset list, and refusal to replace.

# AD-824: Main build wheels are a rolling pre-release

## Decision

Build the six platform wheels when wheel source changes on `main`.
Full verification and the main build call the same wheel workflow.
Each wheel must pass its installed test before publication.
Publish the complete set and its checksums on the `main-build` pre-release.
Move its tag to the built commit. It is not the latest release.
Cancel an older main build when a new one starts. (Superseded by [AD-863](ad-863-the-main-build-release-is-replaced-by-verified-staging-and-rename.md): a started build finishes.)

## Reason

A colleague can install the current development build without a Rust toolchain.
The release workflow keeps the same Full verification and wheel artifacts.

## Alternatives

Building separate wheel matrices duplicates the release build.
Publishing to PyPI would make a development build a public package release.

## Limit

Only the six release platforms are built. A failed build does not publish.
The rolling release is not an archive of past builds.

## Checks

`tests/test_native_ci.py` checks the wheel targets and the Full gate.
`tests/test_main_build.py` checks the wheel set and release notes.

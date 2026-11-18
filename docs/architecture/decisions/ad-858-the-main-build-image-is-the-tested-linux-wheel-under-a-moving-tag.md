# AD-858: The main build image is the tested Linux wheel under a moving tag

## Decision

Publish the container image `ghcr.io/rapiddweller/archkeel` after the six wheels pass.
The image installs the tested `manylinux_2_17_x86_64` wheel of the same run. It compiles nothing.
Push the image first as `sha-<commit>`. Push the moving tag `5.0-rc` only after the smoke test of
the installed wheel passes inside the image and the image label `revision` equals the commit.

Refuse a wheel whose version does not name the built commit.
Skip the move of `5.0-rc` when `main` is already past the built commit.
Reuse an existing `sha-<commit>` image on a rerun. Never delete a tag or a version.

The Dockerfile sets `org.opencontainers.image.source` before the first push. The package then
links to the repository and inherits its access rights.
The image has no PyPI tag, no release tag and no stable name.

## Reason

GitHub Packages has no Python registry. It holds container images, not wheels.
The release page `main-build` stays at its first build (AD-829). The image is the current build.
A failed build or test leaves the old `5.0-rc` unchanged.

## Alternatives

Rebuild the core in the image: slow, and the tested wheel would not be the shipped bits.
Publish `5.0-rc` to PyPI: it makes a development build a public package release.

## Limit

- Only `linux/amd64`. On Apple silicon, run it with `--platform linux/amd64`.
- The first push creates a private package. An organization owner must change its visibility to
  public once; this cannot be undone and has no REST endpoint.
- `5.0-rc` is a constant in `tools/publish_main_image.py`. Change it at the 5.0.0 release.
- The image does not wait for the full CI of `main`. It waits for the wheel jobs and their smoke test.

## Check

`tests/test_main_image.py` checks two commits in a row, a rerun, a failed smoke test, a wheel of
another commit and a newer `main`.

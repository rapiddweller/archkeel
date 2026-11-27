# AD-1275: The main build keeps its newest 30 builds, so an exact pin keeps resolving

Status: accepted. Closes #2183. Amends AD-863.

## Why

AD-863 replaced the six wheels of the `main-build` release with each new build. A consumer that pinned an exact
version (`archkeel==4.0.2.dev952+g585b2e195` in EE CI) got HTTP 404 as soon as the next build was public. A cold
runner failed at the download, before any architecture result. The 5.0.0 release on PyPI will be the real pin. Until
then the dev wheels need a stable URL.

## Decision

1. A new build **adds** its six wheels. It deletes no wheel of an older build, as long as that build is one of the
   newest 30 (`KEEP` in `tools/publish_main_build.py`). Only the older builds are pruned, after the new set is
   public and checked, as AD-863 pruned the old set.
2. The age of a build is the number of commits that lead to its commit (`git rev-list --count`). The history of main
   is linear, so this is the order of publication. The version string is not parsed.
3. A name that is public keeps its bytes (AD-863, unchanged). So a pin keeps its URL and its digest.
4. `SHA256SUMS` lists the digest of every public wheel that stays, the older builds too. A consumer can verify an
   old wheel. The notes of the release say that the newest 30 builds stay and how to pin one.
5. The order of the steps, the staging names, the check before the first public name changes, the rule that an
   older run does not replace a newer build, and the tag move are unchanged.

## Why not a release for each build

A release for each build needs a new tag and a new release object for each of the nightly builds, a second place
to prune and a change of the `--find-links` page that consumers use. Keeping the assets in the one release changes
one function and the notes. The page `expanded_assets/main-build` lists all kept wheels, so
`pip install --pre --find-links <page> archkeel==<version>` finds an old build.

## Counter-examples (each is in `tests/test_main_build.py`)

- A new build next to an older one: both are public, the sums list both, the old digest is the same.
- The 31st build: the oldest build is deleted, the newer 30 stay, a file that is not ours stays.
- A rerun of the same commit: nothing public changes.
- An older run after a newer build: skipped, no change.
- A failure at any step of the publication: the old set stays usable, and a rerun recovers.

## Not done

- The assets of the release grow to 180 files (30 builds, six wheels). The limit of GitHub is 1000.
- The tag `main-build` still points to the newest commit only. A consumer pins a version, not the tag.

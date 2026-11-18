# AD-863: The main build release is replaced by verified staging and rename

Status: accepted (owner decision 2026-11-18). It supersedes [AD-829](ad-829-main-build-publishes-only-a-verified-draft.md)
and replaces its limit "later main builds need a safe replacement design". It keeps AD-824.

## Decision

The release `main-build` and its link `.../releases/expanded_assets/main-build` stay fixed.
There is no Docker image, no new package version and no PyPI upload.
After the six wheels pass their tests, `tools/publish_main_build.py` replaces the set in this order:

1. Check the candidate: six wheels, one version, the version names the built commit, each archive is
   whole, and its `METADATA` carries the same version. Nothing is changed on failure.
2. Read the release. It must be a published pre-release. Its notes name a commit. Collect that commit
   and the commit of every public or staged wheel of ours. Skip the run unless the built commit descends
   from all of them. An older run stops here. A stopped promotion can show newer wheels under old notes,
   so the notes alone do not decide.
3. Upload each new wheel as `<name>.staging`, and `SHA256SUMS.staging`. Pip ignores these names.
   Never overwrite. Delete only a staged file of ours that is incomplete or has another digest, then upload it again.
4. Read the release again. Each staged file must have the digest of the candidate. If not, stop.
   The old set is still the only public set.
5. Rename the staged wheels to their final names. Rename `SHA256SUMS` to `SHA256SUMS.old`,
   then `SHA256SUMS.staging` to `SHA256SUMS`. Write the notes (commit, date, wheel list, the two install commands).
6. Read the release again and compare every digest. Then move the tag `main-build` to the commit.
7. Delete only obsolete files of ours: wheels of another version, `*.staging`, `SHA256SUMS.old`.
   Any other asset stays.

`SHA256SUMS` lists the digests that the release shows for the public wheels. A name that is already public keeps its bytes.
A rerun of the same commit may build other bytes. They are not published.

## Reason

GitHub has no atomic replacement of several assets. A wheel name holds the commit, so a new wheel never
collides with an old wheel. The fixed pip link therefore always finds a complete set for each platform,
because the old wheels go only after the new ones are public and checked. A rename changes the name of
one asset in one call. The new wheels appear for pip only after all six are staged and checked.

## Limits

- The rename of six wheels is not atomic. If it stops, pip can see some new and some old wheels.
  Each wheel was tested on its own. The next run completes the rename.
- For about two calls, `SHA256SUMS` is missing or lists the previous set. `SHA256SUMS.old` keeps the previous list until the end.
- A user who downloads an old wheel while it is deleted gets a 404 once.
- Serialization: the wheel build has the group `main-build-wheels`. A newer push cancels an older build.
  The publish job has the group `main-build-publish` without cancel. A started publication runs to its end.
  The newest waiting publication replaces older waiting ones. There is no workflow-wide group, because
  it would cancel a started publication. A manual cancel or a crash can still stop a run in any step.
  Every step can be repeated, so the next run completes or cleans the state.
- Checked by GET on the public release (2026-11-18): the asset name keeps `+`, the download link has `%2B`,
  the page lists the same names after unquoting, `digest` is `sha256:<hex>` and equals the file, `state` is
  `uploaded`, and the notes parser and `SHA256SUMS` text match the live files. The rename, the upload of a
  `.staging` name, the digest of an incomplete upload and the move of the tag are checked only with a fake.

## Alternatives

A draft release with the same tag: GitHub does not say if a draft can share a tag name with a published release.
Upload with `--clobber`: it deletes the old asset first and leaves a gap.
Upload the new wheels directly under their final names: pip can see an incomplete set.

## Check

`tests/test_main_build.py` checks two builds in a row, a rerun, an older run, an older run after a stopped
promotion (public and staged newer wheels), a failure at every mutation including a partial upload, a damaged
upload, a bad candidate, the release type, the live name rules and the workflow groups.

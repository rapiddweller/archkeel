# AD-476: A release publishes each platform wheel that Full builds and runs

## Status

Accepted. Part of #880. It supersedes point 8 of AD-436 and the closed release of AD-432.

## Reason

AD-436 closed the release while the Windows core refused each root. AD-442 corrected the root
path, and AD-476 follows it: Full run 43574544527 on main was green in every job, including the
Windows wheel job, which installs the wheel alone and requires the result of the checkout core
(exit code, status, code digest and the whole frame). No platform gives "no verdict" now, so the
guard that said so is removed.

## Decision

- `PUBLISH_NATIVE_WHEELS` and the first job `core-in-wheel` are removed from `release.yml`.
  `verify` (Full) is the first job.
- `NO_VERDICT` and its cause text are removed from `tools/release_core.py`.
- A release is exactly the sdist and the six platform wheels of `PLATFORM_TAGS`. The build step
  refuses another count, a wheel without a platform, and (new) a set of wheels whose platforms are
  not exactly `PLATFORM_TAGS` (`tools/release_core.py`).
- `tests/test_native_ci.py` fails when a platform of `PLATFORM_TAGS` is not built and run by a job
  of Full, or when such a job is not in the needs of `verified`.

## The release path

1. A tag runs Full (`verify`). Each platform job builds its wheel, checks tag, content and SBOM,
   installs it alone and runs the tests of the installed wheel.
2. `build` builds the sdist, downloads the six wheels, and refuses a count other than 6 + 1.
3. `tools/release_core.py` checks that each wheel holds the core and a digest of the same bytes,
   that the platforms are exactly the six, and installs the wheel of the build host alone.
4. `publish` verifies the draft assets, then PyPI, then the GitHub release. At run time the shell
   checks the digest of the binary before it starts it (`cli/core_binary.py`).

## Limits

- The Windows wheel writes no report file: `report --output` refuses with `io_error` (AD-440).
- The build host checks one wheel alone (manylinux x86_64). The other five are checked only by
  their own Full job, on their own platform, from the same tag.
- This change publishes nothing and creates no tag.

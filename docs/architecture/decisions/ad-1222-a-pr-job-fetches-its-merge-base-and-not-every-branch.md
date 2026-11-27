# AD-1222: A PR job fetches its merge base and not every branch

Status: accepted. From the gate reviews of 2026-11-27.

## Why

The PR base job and the area jobs checked out with `fetch-depth: 0`. That fetches about 1,650 remote
branches (about 2,000 log lines) in each of about 8 jobs. The jobs read only the merge base with the
base commit, `origin/main` and a few first-parent ancestors of the base.

## What the jobs read

- `tools/select_areas.py`, `tools/native_touched.py`: `git diff <base>...HEAD`.
- `tools/self_check_gate.py`, `tools/self_check_shell.py`: `git merge-base <base> HEAD`, `git show`,
  `git ls-tree`, a worktree of the base, and `git diff` between earlier main commits (the base-result reuse).
- `pr-gate.yml`: `git rev-list --first-parent -n 8 <base>^`.
- `tests/test_born_small.py`: `git diff origin/main...HEAD`. It skips without `origin/main`.
- `tests/test_doc_references_exist.py`: `git log --all --name-only` (the paths that history deleted). Its
  area `self-check and CI` fetches the whole commit graph (`--whole`), still without blobs and branches.
- No test or tool of these jobs reads a tag. The version comes from `hatch-vcs` and is `0.1.dev1+g<sha>`
  in a shallow clone; no test of these jobs reads it. Wheel, sdist and release jobs keep full history.

## Decision

1. The PR base job and the area jobs of a PR check out with `fetch-depth: 1`. A push to `main` keeps `0`.
2. `tools/fetch_history.py <base-sha>` then fetches `main` (as `origin/main`), the base commit and `HEAD`
   without blobs and without tags, with the depths 20, 100 and 500, then the whole commit graph.
3. It stops when the base commit is an ancestor of `HEAD`. Then the merge base is the base commit, exactly.
   A missing edge of a shallow history can hide an ancestor, never invent one. At depth 4 of the test
   history, `git merge-base` gave an older commit and not the base: the check is the ancestry, not the
   exit code of `git merge-base`.
4. When no depth shows it, the whole graph gives the exact merge base. When there is none, or the fetch
   fails, the tool exits 1 and the job fails. It never goes on with a wrong base.

A shallow merge base with `origin/main` can be older than the true one. A diff from it holds more paths,
never fewer, so the selection of areas and the new-file check stay safe.

## Rejected

- `--depth=1` plus one `git fetch origin main <base>` without a check: a shallow `merge-base` can be wrong.
- `fetch-depth: 0` with a narrow refspec: the action has no such option.

## Checks

`tests/test_fetch_history.py`: the merge base at a depth that is enough, a depth that only looks enough, a
base outside the history, a base with no common history (exit 1).

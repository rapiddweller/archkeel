# Regular Git Blob Kind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four duplicated raw Git mode/object-tag decisions with one owned nominal ingress, preserving exact accepted wire pairs and errors.

**Architecture:** Existing check.snapshot owns the low-level immutable revision input. check.git already imports it. A RegularGitBlobKind enum owns only REGULAR=(b"100644", b"blob") and EXECUTABLE=(b"100755", b"blob"); regular_git_blob_kind(mode: bytes, kind: bytes) -> RegularGitBlobKind | None converts this pair once. Both existing parsers keep their split/path/OID/error order and use the shared classification at the current regular-blob check.

**Tech Stack:** Python stdlib Enum, existing native collector/HRC/UML Target, pytest and real Git fixtures, GitHub Actions only.

**Spec:** Approved bounded #542 design; base bb3e498b9c43afc954ef9fe7078595983e0b3c2f. Exact original native artifact12083429473 indices68/228/246/474; current AST association39000428731/job117301992685.

## Global Constraints

- Exactly two production files: check/snapshot.py and check/git.py; no new production module, DTO, wrapper framework, full Git tree model, wire-record closure or duplicate enum.
- Shared dependency stays git -> snapshot. File names, paths, revisions and object IDs stay open data.
- Only the two existing exact byte pairs are supported. Unknown modes/object kinds, symlinks, submodules and alternate spellings stay rejected.
- Preserve GitError/MissingBlobError/SnapshotError text, malformed metadata behavior and selection-before-validation ordering.
- No new Issue/PR or own reviewer: Root owns final #542 union/fullsuite/Astra/Main. No manual budget rise or unrelated source writes.

## Review Focus

- Normal/executable files preserve exact payload/archive bytes, including committed metadata.
- Symlink/submodule/tree and malformed/future mode/object tags cannot become accepted.
- Unselected invalid paths remain ignored; selected invalid paths keep existing errors.
- Independent authored API Target detects return/parameter widening; native raw-byte dispatch is actually witnessed, not inferred from capability labels.
- Source and native call/UNKNOWN evidence stay honest; final baseline comes from the normal tool.

### Task 1: Durable RED and actual byte coverage

- [ ] Author the small enum/function Target and scoped guards in the existing check contract; protect real producer/consumer functions, not generated expected observations.
- [ ] Add tests/test_git_blob_types.py with missing-port/nominal API positives, unchanged-target widening/raw-byte mutations and real committed Git regular/executable/symlink/submodule cases.
- [ ] Run hosted RED before production; separately verify real legacy byte comparisons have trace-valid guard failures. If byte detection is missing, notify Root and do not add a special detector here.

### Task 2: One coherent production increment

- [ ] Add the enum and exact optional classification port to check.snapshot.
- [ ] Replace only the existing mode/kind conditional in snapshot and git; leave split, filtering, OID decoding and local errors intact.
- [ ] Run GREEN, existing snapshot/Git/ordering/initial-PR/validation regressions, strict typing, Ruff, formatting and hygiene.
- [ ] Add the new test file to the existing required Makefile selection.

### Task 3: Freeze for Root union

- [ ] Compare real Git fixture outputs before/after and exact native site/UNKNOWN evidence against the pinned base.
- [ ] Generate any required normal intent receipt, validate committed source without writing, and retain measured bounds without manual policy changes.
- [ ] Deliver exact source/files/check links. Root runs combined fullsuite and one final holistic Astra review.

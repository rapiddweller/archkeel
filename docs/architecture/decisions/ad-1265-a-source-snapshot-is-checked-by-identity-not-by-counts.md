# AD-1265: A source snapshot is checked by identity, not by counts

Status: accepted. Part of the drift-gates audit of 2026-11-27 (family C).

## Why

`tests/test_project_demo_snapshots.py` pinned the number of files of each project demo (111, 89 and 22
Dart files, 37 manifests, 125, 85, 79, 72, 7, 5 for the Python app, 45, 42, 39, 6 and 41 for the Nest
app, 17, 43 and 84,616 bytes for the resolver inputs). The same file already compares each list with
the files on disk and with the upstream tree. A count adds nothing to that, and a legitimate refresh
of a snapshot must edit each number by hand.

## Decision

The count literals are deleted, in this file and in `test_report_gallery_cards.py` (37 pubspec files).
Kept: the repository and commit of each snapshot, each `sha256` and git blob hash against the file on
disk, the set equality of the listed paths with the files on disk, the named exclusion lists, the
parent library of each generated Dart file, and the rule that resolver inputs stay outside the
application scope.

## The truth each count asserted, and where it is tested

| Count | Truth | Test now |
|---|---|---|
| Dart files, libraries, generated parts | the fixture is the pinned snapshot | `actual_dart == {paths in SNAPSHOT.json}`, hash of each file, parent library rule |
| 37 pubspec files | the workspace is complete | set equality of on-disk manifests with the listed ones; root and app pubspec present |
| 125, 85, 79, 72, 7, 5 (Python) | the upstream tree and the selection | `selected` flag rule, exact root allowlist, set equality of `app/`, blob hash against upstream |
| 45, 42, 39, 6, 41 (Nest) | original and derived inputs | exact excluded list, derived map, set equality of `src/` |
| 17, 43, 84,616 (resolver inputs) | each input is pinned | size and hash of each recorded file, unique lock locators |

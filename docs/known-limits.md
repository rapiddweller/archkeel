# Known limits: unresolved calls

Historical Pledge evidence. Names and commands below refer to the pinned checker, before the renames to Codekeel and Archkeel.

FACT — Every `pledge@<SHA>` below is a commit in this repository's history before the Codekeel and Archkeel rename commits.

FACT — This diagnosis measures committed sources. It changes no resolver, contract, or check policy.

## Sources and reproduction

| FACT: Input | Immutable source | Producer Python |
|---|---|---|
| D-self and Pledge checker | `pledge@f5aaca35d1934e17ef3eb13ae3e1c3180a3a37b8` | 3.11.12 |
| Repo #2 | internal 13-component service at `74b3271133620983bb4be9a766850a2abc06073f` | 3.12.10 |
| EE producer | `datamimic-ee@dc7526592073985ed69902b21d6a1c861ac02fa0` | Same as each report |

FACT — `tools/classify_unresolved.py` at `pledge@19e91a1f00b93ebf7b5b9b8fe535d3869a70e407` emits a summary and the complete call ledger. It checks Python version, source digest, file count, unique call IDs, and exact AST matches. Its SHA-256 is checked before execution below. It is outside the package and `make check`.

Set `PLEDGE_REPO` to a clone of this repository, and `REPO2_REPO` and `EE_REPO` to local repositories containing those commits. Set `PY311` and `PY312` to Python 3.11.12 and 3.12.10 with Pledge's `packaging` dependency installed. Run the following in one Bash session:

```bash
set -euo pipefail
PLEDGE_SHA=f5aaca35d1934e17ef3eb13ae3e1c3180a3a37b8
REPO2_SHA=74b3271133620983bb4be9a766850a2abc06073f
EE_SHA=dc7526592073985ed69902b21d6a1c861ac02fa0
WORK=$(mktemp -d)
export GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1
archive() {
    mkdir -p "$3"
    git -C "$1" archive "$2" | tar -xf - -C "$3"
    git -C "$3" init -q
    git -C "$3" fetch -q --depth=1 "$1" "$2"
    git -C "$3" reset -q --mixed FETCH_HEAD
    test "$(git -C "$3" rev-parse HEAD)" = "$2"
}
archive "$PLEDGE_REPO" "$PLEDGE_SHA" "$WORK/pledge"
archive "$REPO2_REPO" "$REPO2_SHA" "$WORK/repo2"
mkdir -p "$WORK/producer" "$WORK/repo2/docs/architecture"
git -C "$EE_REPO" archive "$EE_SHA" script/__init__.py script/architecture |
    tar -xf - -C "$WORK/producer"
```

FACT — The source files come from `git archive`. Temporary Git metadata supplies the HEAD/status required by `src/pledge/check/report.py:52`; `reset --mixed` updates only temporary metadata. The original Repo #2 working tree is neither read as scan input nor modified.

Write the following unchanged 5b configuration to `$WORK/repo2/pledge.toml`:

```toml
[scan]
roots = ["svc"]
namespace = "svc"
contract = "docs/architecture/architecture-contract.json"
```

Write this zero-rule contract to `$WORK/repo2/docs/architecture/architecture-contract.json`:

```json
{
  "capabilities": [
    {
      "id": "CAP-APP",
      "label": "Application",
      "name": "application",
      "provenance": [
        "docs/architecture/architecture-contract.json"
      ],
      "review_order": 1
    }
  ],
  "components": [],
  "context_roots": [],
  "context_roots_provenance": [
    "docs/architecture/architecture-contract.json"
  ],
  "paths": [],
  "public_api": [],
  "public_api_provenance": [
    "docs/architecture/architecture-contract.json"
  ],
  "public_commands": [],
  "review_scopes": [],
  "rules": [],
  "schema_version": "1.1.0",
  "spot_owners": []
}
```

```bash
export PYTHONPATH="$WORK/pledge/src"
"$PY311" -c 'import platform; assert platform.python_version() == "3.11.12"'
"$PY312" -c 'import platform; assert platform.python_version() == "3.12.10"'
git -C "$PLEDGE_REPO" show 19e91a1f00b93ebf7b5b9b8fe535d3869a70e407:tools/classify_unresolved.py > "$WORK/classify_unresolved.py"
CLASSIFIER_SHA256=ee626f8f2b7e13baa41bcad7d3195c3b19e122b6661b938460c319ed351b6a9e
"$PY311" - "$WORK/classify_unresolved.py" "$CLASSIFIER_SHA256" <<'PYTHON'
import hashlib, pathlib, sys
assert hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest() == sys.argv[2]
PYTHON
measure() {
    "$2" -m pledge.cli report --root "$WORK/$1" \
        --producer-root "$WORK/producer" --output "$WORK/$1-report.json" \
        > "$WORK/$1-result.json"
    "$2" "$WORK/classify_unresolved.py" --root "$WORK/$1" \
        --report "$WORK/$1-report.json" --output "$WORK/$1-analysis.json"
}
measure pledge "$PY311"
measure repo2 "$PY312"
```

FACT — Both reports and both classifier runs exited 0. Each scan discovered, read, and parsed every scoped file; both returned `diagnostics = []` and `violations = []`. The added Repo #2 configuration makes its temporary snapshot dirty; its Python source digest still identifies only committed files.

| FACT: Report result | D-self | Repo #2 |
|---|---:|---:|
| Files discovered / read / parsed | 28 / 28 / 28 | 67 / 67 / 67 |
| `calls_total` | 1322 | 4318 |
| Unresolved / total | 237 / 1322 (17.93%) | 998 / 4318 (23.11%) |
| Partially resolved (excluded below) | 60 | 380 |
| Unmatched unresolved records | 0 | 0 |
| Source digest | `7ddaddc7c9009c80898f20a9c0555af3b1f9ebff0cfe93d1ef41565314eb4d73` | `239326f54a8865aa052295fbf0b76f0bffb1a16b912b39cc82af7821b68e988a` |

## Method

FACT — Count each call record with `data.status == "unresolved"` once, not runtime executions. Match it to `ast.Call` by file, start/end line, column, and `ast.unparse(call.func) == data.expression`; nested calls can share a start position. All 237 and 998 records matched uniquely (`tools/classify_unresolved.py`).

FACT — A pattern is the immediate AST type of `Call.func`, plus the type of its receiver for `Attribute`. Classes are disjoint. `Attribute(Name)` covers `x.m()` without claiming that `x` is a Protocol, dataclass, or container. Percentages below use all unresolved records in that repo as denominator, rounded to two decimals.

## D-self

| FACT: Rank / syntax | Count | Share of unresolved | Quote + file:line at the source SHA |
|---|---:|---:|---|
| 1. `Attribute(Name)` | 160 | 67.51% | `pending.pop()` — `src/pledge/check/delta.py:105` |
| 2. `Attribute(Call)` | 31 | 13.08% | `key.replace("_", " ").title()` — `src/pledge/check/delta.py:287` |
| 3. `Name` | 18 | 7.59% | `producer(` — `src/pledge/check/report.py:45` |
| 4. `Attribute(Attribute)` | 9 | 3.80% | `path.parent.mkdir(parents=True, exist_ok=True)` — `src/pledge/check/report.py:59` |
| 5. `Attribute(Subscript)` | 8 | 3.38% | `old_groups[item.logical_fingerprint].append(item)` — `src/pledge/check/delta.py:325` |

FACT — Top five: 226/237 = 95.36%. Remaining forms: `Attribute(Constant)` 5 (2.11%); `Attribute(BinOp)` 4 (1.69%); `Attribute(Set)` 1 (0.42%); `Attribute(Dict)` 1 (0.42%).

## Repo #2

| FACT: Rank / syntax | Count | Share of unresolved | Quote + file:line at the source SHA |
|---|---:|---:|---|
| 1. `Attribute(Call)` | 385 | 38.58% | `value.strip().lower()` — `svc/c03/n8366.py:804` |
| 2. `Attribute(Name)` | 382 | 38.28% | `data.get("p")` — `svc/c03/n10850.py:43` |
| 3. `Attribute(Await)` | 116 | 11.62% | `(await n3540.n10594(n3206)).scalars()` — `svc/c03/n8282.py:155` |
| 4. `Attribute(Attribute)` | 68 | 6.81% | `row.name.lower()` — `svc/c03/n8366.py:156` |
| 5. `Name` | 23 | 2.30% | `n13587(message)` — `svc/c09/handlers.py:69` |

FACT — Top five: 974/998 = 97.60%. Remaining forms: `Attribute(JoinedStr)` 8 (0.80%); `Attribute(Subscript)` 8 (0.80%); `Attribute(Constant)` 7 (0.70%); `Attribute(Dict)` 1 (0.10%).

## Comparison and resolver boundary

FACT — The top-five sets and their order within each repo are unchanged from 5c. Four forms overlap: `Attribute(Name)`, `Attribute(Call)`, `Attribute(Attribute)`, and `Name`. D-self additionally has `Attribute(Subscript)` (8); Repo #2 has `Attribute(Await)` (116). D-self has no Await receivers; Repo #2 has 8 Subscript receivers outside its top five.

FACT — The numbers changed: D-self went from 234/1318 to 237/1322 after Step H. The committed Repo #2 snapshot has 67 files and 998/4318 unresolved, replacing the previous dirty working-tree measurement of 74 files and 1512/6368. These are different source inputs, not evidence of resolver improvement. Previous values are recorded in `pledge@f5aaca3:docs/known-limits.md`.

FACT — Shared scanner limits remain visible, with different weights: D-self is dominated by `Attribute(Name)` (160/237); Repo #2 has 385 Call-result and 116 Await-result receivers (501/998). Syntax alone does not establish that those calls are SQL operations or have the same semantic cause.

| FACT: Report reason | D-self | Repo #2 | EE producer branch at the pinned SHA |
|---|---:|---:|---|
| `dynamic attribute receiver` | 169 | 450 | `script/architecture/scanner.py:593–617` |
| `call target is a dynamic expression` | 50 | 525 | `script/architecture/scanner.py:486–495`, `:618` |
| `name has no statically indexed binding` | 18 | 23 | `script/architecture/scanner.py:573–591` |

FACT — `_resolve` checks indexed names, import aliases, builtins, and simple attribute chains. It does not use argument annotations, local assignments, or return types (`script/architecture/scanner.py:573–618`). Call/Await/Subscript/literal receivers fail `_dotted_expression` and reach the dynamic-expression branch. That classification does not prove runtime unpredictability.

FACT — Import-alias attributes are resolved directly; internal method-name matches can already classify a dynamic receiver as partially resolved (`script/architecture/scanner.py:595–616`). Partially resolved calls are excluded here. This diagnosis measures scanner resolution, not architecture quality.

## Open claims

UNKNOWN — How many `Attribute(Name)` receivers are Protocols, dataclasses, or other concrete types; this classifier measures syntax, not types.
UNKNOWN — Which additional targets another resolver could determine correctly; no alternative resolver was run.
HYPOTHESIS — Unresolved share might rise with code “modernity”. Two different repos, scopes, and Python versions do not establish that relationship; modernity has not been defined or measured.
UNKNOWN — The right check policy; the measured historical outcomes below do not establish feature correctness.

# Known limits: unresolved calls

Historical Pledge evidence. Names and commands below refer to the pinned checker, before the renames to Codekeel and Archkeel.

FACT — Every `pledge@<SHA>` below is a commit in this repository's history before the Codekeel and Archkeel rename commits.

FACT — This diagnosis measures committed sources. It changes no resolver, contract, or check policy.

## Sources and reproduction

| FACT: Input | Immutable source | Producer Python |
|---|---|---|
| D-self and Pledge checker | `pledge@094551b0d5cc9d38c843a7f710df93cff731d3a1` | 3.11.12 |
| Repo #2 | `rd-svc-window-cleaning@74b3271133620983bb4be9a766850a2abc06073f` | 3.12.10 |
| EE producer | `datamimic-ee@dc7526592073985ed69902b21d6a1c861ac02fa0` | Same as each report |

FACT — `tools/classify_unresolved.py` at `pledge@4d46c80b6ce3ef88d7509dde7a802a515f5b89fe` emits a summary and the complete call ledger. It checks Python version, source digest, file count, unique call IDs, and exact AST matches. Its SHA-256 is checked before execution below. It is outside the package and `make check`.

Set `PLEDGE_REPO` to a clone of this repository, and `REPO2_REPO` and `EE_REPO` to local repositories containing those commits. Set `PY311` and `PY312` to Python 3.11.12 and 3.12.10 with Pledge's `packaging` dependency installed. Run the following in one Bash session:

```bash
set -euo pipefail
PLEDGE_SHA=094551b0d5cc9d38c843a7f710df93cff731d3a1
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
roots = ["backend"]
namespace = "backend"
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
git -C "$PLEDGE_REPO" show 4d46c80b6ce3ef88d7509dde7a802a515f5b89fe:tools/classify_unresolved.py > "$WORK/classify_unresolved.py"
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
| 1. `Attribute(Call)` | 385 | 38.58% | `value.strip().lower()` — `backend/services/disposition_queries.py:804` |
| 2. `Attribute(Name)` | 382 | 38.28% | `data.get("p")` — `backend/services/pagination.py:43` |
| 3. `Attribute(Await)` | 116 | 11.62% | `(await session.execute(order_query)).scalars()` — `backend/services/mobile_sync.py:155` |
| 4. `Attribute(Attribute)` | 68 | 6.81% | `row.name.lower()` — `backend/services/disposition_queries.py:156` |
| 5. `Name` | 23 | 2.30% | `callback(message)` — `backend/orchestrator/handlers.py:69` |

FACT — Top five: 974/998 = 97.60%. Remaining forms: `Attribute(JoinedStr)` 8 (0.80%); `Attribute(Subscript)` 8 (0.80%); `Attribute(Constant)` 7 (0.70%); `Attribute(Dict)` 1 (0.10%).

## Comparison and resolver boundary

FACT — The top-five sets and their order within each repo are unchanged from 5c. Four forms overlap: `Attribute(Name)`, `Attribute(Call)`, `Attribute(Attribute)`, and `Name`. D-self additionally has `Attribute(Subscript)` (8); Repo #2 has `Attribute(Await)` (116). D-self has no Await receivers; Repo #2 has 8 Subscript receivers outside its top five.

FACT — The numbers changed: D-self went from 234/1318 to 237/1322 after Step H. The committed Repo #2 snapshot has 67 files and 998/4318 unresolved, replacing the previous dirty working-tree measurement of 74 files and 1512/6368. These are different source inputs, not evidence of resolver improvement. Previous values are recorded in `pledge@094551b:docs/known-limits.md`.

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

## Regression check on real history

FACT — `evaluate_expectation()` unconditionally appends `compare_ratchets()` failures before checking declarations: `failures = list(compare_ratchets(ratchets.baseline, ratchets.head))` (`src/pledge/check/expectation.py:250`). `selected_changes` never removes them (`:251–265`). An expectation currently cannot allow an unresolved-count increase.

### Inputs and method

FACT — Checker: `pledge@b6ebc0394bc4d6ed090ed1f72dd14b063f7f73cf`; producer: `datamimic-ee@dc7526592073985ed69902b21d6a1c861ac02fa0`; Python 3.12.10 throughout. Repo #2 starts from `main@74b3271133620983bb4be9a766850a2abc06073f`; EE starts from `development@dc7526592073985ed69902b21d6a1c861ac02fa0` (no local `main`). Scan roots/namespaces are `backend` and `datamimic_ee`, respectively.

FACT — Walk `git rev-list --first-parent <start-SHA>`, retain commits with a nonempty `git diff --numstat <SHA>^1 <SHA> -- <scan-root>`, and take at most 20/10. Repo #2 has only 17 qualifying commits among 27 first-parent commits; 16 pairs are comparable. EE supplies all 10 requested pairs. Diff lines below are additions plus deletions for all files under the root, including non-Python files; renames retain Git's detection.

FACT — Each distinct source SHA was materialized with `git archive`; shared pair endpoints reused the same report. Repo #2 used the unchanged zero-rule configuration above. EE used its versioned contract at `docs/architecture/architecture-contract.json`; its digest is identical across the 13 measured SHAs. EE archives must include `AGENTS.md`, `datamimic_ee`, `docs`, and `pyproject.toml` so contract provenance exists. Original working trees were not scanned or modified.

Reproduce each endpoint with the archive/report/classifier commands above, setting the source SHA to the table entry and its `^1` parent. For EE, use `[scan] roots = ["datamimic_ee"], namespace = "datamimic_ee", contract = "docs/architecture/architecture-contract.json"`. Load each report and compare using the existing functions:

```python
from pledge.check.ratchets import compare_ratchets, measure_python_ratchets
from pledge.ir.codec import decode_canonical_model, parse_observation
import json

def measurements(path):
    return measure_python_ratchets(parse_observation(decode_canonical_model(json.loads(path.read_bytes()))))

failures = compare_ratchets(measurements(parent_report), measurements(commit_report))
```

FACT — This measures scalar/ratio rejection only, not the full `pledge check`. No host ordering, lock validation, expectation or fingerprint gates were executed. Each parent acts as the measurement baseline; it is not claimed to be the last accepted lock state. Ratios use raw cross multiplication (`src/pledge/check/ratchets.py:80–100`). No valid endpoint has a zero denominator.

### Commit comparisons

#### Repo #2

| FACT: SHA | Diff +/− (total) | calls_total before → after | calls_unresolved before → after | Failing checks and values | Commit subject |
|---|---:|---:|---:|---|---|
| `74b32711` | +2494/−90 (2584) | 3530 → 4318 | 728 → 998 | calls_unresolved: 728→998; typing_positions: 33→36; unresolved_ratio: 728/3530→998/4318 | Implement operable disposition workflow |
| `dc0ac35c` | +5969/−303 (6272) | 2007 → 3530 | 363 → 728 | calls_unresolved: 363→728; typing_positions: 26→33; unresolved_ratio: 363/2007→728/3530 | Implement durable operational cleaning workflow |
| `87109723` | +1444/−63 (1507) | 1598 → 2007 | 249 → 363 | calls_unresolved: 249→363; unresolved_ratio: 249/1598→363/2007 | Implement three-role planning product slice |
| `6e251257` | +389/−88 (477) | 1499 → 1598 | 205 → 249 | calls_unresolved: 205→249; unresolved_ratio: 205/1499→249/1598 | Initial commit |
| `165a7611` | +914/−0 (914) | 1253 → 1499 | 171 → 205 | calls_unresolved: 171→205; typing_positions: 25→32; unresolved_ratio: 171/1253→205/1499 | feat: add durable taskiq planning orchestrator |
| `5688e298` | +487/−23 (510) | 1163 → 1253 | 170 → 171 | calls_unresolved: 170→171; typing_positions: 20→25 | feat: complete api application contracts |
| `4859da27` | +235/−1 (236) | 1103 → 1163 | 154 → 170 | calls_unresolved: 154→170; typing_positions: 17→20; unresolved_ratio: 154/1103→170/1163 | feat: persist durable process execution state |
| `e3b506d7` | +46/−0 (46) | 1103 → 1103 | 154 → 154 | none | fix: add durable process state contracts |
| `10aae8a5` | +83/−35 (118) | 1076 → 1103 | 151 → 154 | calls_unresolved: 151→154 | fix: plan weekly capacity across workdays |
| `9318f51c` | +228/−13 (241) | 1033 → 1076 | 149 → 151 | calls_unresolved: 149→151 | feat: delegate supported api reads |
| `23e12d8d` | +851/−0 (851) | 828 → 1033 | 128 → 149 | calls_unresolved: 128→149 | feat: implement planning application services |
| `266c4442` | +853/−0 (853) | 553 → 828 | 64 → 128 | calls_unresolved: 64→128; typing_positions: 8→17; unresolved_ratio: 64/553→128/828 | feat: implement tenant scoped repositories |
| `a0400c57` | +508/−0 (508) | 389 → 553 | 29 → 64 | calls_unresolved: 29→64; typing_positions: 7→8; unresolved_ratio: 29/389→64/553 | feat: implement geo matrix and tour solver |
| `e52d2c77` | +16/−1 (17) | 389 → 389 | 29 → 29 | none | fix: complete planning adapter contracts |
| `7d17901b` | +25/−4 (29) | 386 → 389 | 29 → 29 | none | fix: persist proposals and link process runs |
| `462ad498` | +29/−5 (34) | 378 → 386 | 29 → 29 | none | fix: carry planning inputs across ports |
| `b5ba2765` | +1524/−0 (1524) | UNKNOWN → 378 | UNKNOWN → 29 | UNKNOWN: parent report Exit 2 | feat: freeze planning engine contracts |

FACT — 12/16 comparable pairs rejected; 1 UNKNOWN pair. Only absolute unresolved: 3; only ratio: 0.

#### EE

| FACT: SHA | Diff +/− (total) | calls_total before → after | calls_unresolved before → after | Failing checks and values | Commit subject |
|---|---:|---:|---:|---|---|
| `df869a07` | +475/−113 (588) | 32356 → 32510 | 3418 → 3410 | none | Merge branch 'fix/4.0-compat-aliases-and-entity-metadata' into 'development' |
| `4657a666` | +339/−42 (381) | 32286 → 32356 | 3416 → 3418 | calls_unresolved: 3416→3418; cycle_edges: 419→422 | Merge branch 'feat/legacy-xml-compatibility' into 'development' |
| `c799b024` | +5/−1 (6) | 32284 → 32286 | 3416 → 3416 | none | Merge branch 'DAT-1597-error-id-not-allowed-in-generate' into 'development' |
| `12a82eed` | +7/−6 (13) | 32282 → 32284 | 3415 → 3416 | calls_unresolved: 3415→3416; unresolved_ratio: 3415/32282→3416/32284 | Merge branch 'fix/surface-redis-log-handler-failures' into 'development' |
| `ccefa562` | +177/−114 (291) | 32261 → 32282 | 3415 → 3415 | none | Merge branch 'fix/align-postgres-test-database' into 'development' |
| `44b4e7b2` | +13/−1 (14) | 32260 → 32261 | 3415 → 3415 | none | Merge branch 'feat/mongodb-tls-passthrough' into 'development' |
| `09c188d9` | +19/−26 (45) | 32261 → 32260 | 3415 → 3415 | unresolved_ratio: 3415/32261→3415/32260 | Merge branch 'feat/object-storage-tls' into 'development' |
| `027d880b` | +21/−41 (62) | 32262 → 32261 | 3413 → 3415 | calls_unresolved: 3413→3415; unresolved_ratio: 3413/32262→3415/32261 | Merge branch 'feat/config-spot-cleanup' into 'development' |
| `b806683d` | +59/−69 (128) | 32276 → 32262 | 3414 → 3413 | unresolved_ratio: 3414/32276→3413/32262 | Merge branch 'feat/dm-infrastructure-variable-aliases' into 'development' |
| `981f34e3` | +35/−4 (39) | 32266 → 32276 | 3413 → 3414 | calls_unresolved: 3413→3414; typing_positions: 2463→2464 | Merge branch 'feat/authoring-traversal-count-roundtrip' into 'development' |

FACT — 6/10 comparable pairs rejected; 0 UNKNOWN pairs. Only absolute unresolved: 0; only ratio: 2.

| FACT: Failing dimension (overlapping pairs) | Repo #2 / 16 | EE / 10 |
|---|---:|---:|
| `calls_unresolved` | 12 | 4 |
| `unresolved_ratio` | 8 | 4 |
| `typing_positions` | 7 | 1 |
| `cycle_edges` | 0 | 1 |
| `private_crossings` | 0 | 0 |
| `violations` | 0 | 0 |
| `coverage_failures` | 0 | 0 |

FACT — EE `09c188d9` keeps unresolved at 3415 but reduces total calls from 32261 to 32260; the ratio alone fails. EE `b806683d` reduces unresolved from 3414 to 3413, yet the denominator falls enough for the ratio alone to fail. Repo #2's three absolute-only failures are `10aae8a5`, `9318f51c`, and `23e12d8d`; their ratios do not increase.

### Added unresolved record patterns

FACT — Run `tools/classify_unresolved.py` on both endpoints. For every pair rejected on absolute unresolved, subtract multisets keyed by `(kind, source_module, source_scope, expression, reason)` from the IR call records with `status == "unresolved"`; use classifier call IDs to attach AST patterns. Evidence IDs and positions are excluded from cross-commit matching. Scope/name changes can count as removal plus addition; duplicate occurrences retain multiplicity. Examples below are representatives of added groups, not proof of a unique newly introduced runtime call site.

FACT — For each pair, `added - removed == unresolved_after - unresolved_before`. These are observation-record changes, not semantic equivalence or runtime execution counts. The tables include every pattern in every absolute-count rejection, without top-five truncation. Target excerpts come from `ast.unparse(call.func)`; `…` abbreviates long expressions.

#### Repo #2: additions

| FACT: SHA | Added / removed | Pattern | Count | Target excerpt + file:line at that SHA |
|---|---:|---|---:|---|
| `74b32711` | 270 / 0 | `Attribute(Call)` | 115 | `value.strip().lower` — `backend/services/disposition_queries.py:804` |
| `74b32711` | 270 / 0 | `Attribute(Name)` | 99 | `data.get` — `backend/services/pagination.py:41` |
| `74b32711` | 270 / 0 | `Attribute(Await)` | 34 | `(await self._session.execute(statement)).scalar_one` — `backend/services/disposition_queries.py:735` |
| `74b32711` | 270 / 0 | `Attribute(Attribute)` | 18 | `row.name.lower` — `backend/services/disposition_queries.py:156` |
| `74b32711` | 270 / 0 | `Attribute(Subscript)` | 2 | `addresses[row.objekt_id].lower` — `backend/services/disposition_queries.py:330` |
| `74b32711` | 270 / 0 | `Name` | 2 | `mapper` — `backend/services/disposition_queries.py:871` |
| `dc0ac35c` | 425 / 60 | `Attribute(Call)` | 168 | `str(stoerung_id).encode` — `backend/services/disturbance_commands.py:176` |
| `dc0ac35c` | 425 / 60 | `Attribute(Name)` | 139 | `busy.get` — `backend/services/planning_execution.py:346` |
| `dc0ac35c` | 425 / 60 | `Attribute(Await)` | 69 | `(await session.execute(order_query)).scalars` — `backend/services/mobile_sync.py:155` |
| `dc0ac35c` | 425 / 60 | `Attribute(Attribute)` | 36 | `uow.session.add` — `backend/services/customer_portal.py:209` |
| `dc0ac35c` | 425 / 60 | `Attribute(Constant)` | 5 | `'.'.join` — `backend/main.py:80` |
| `dc0ac35c` | 425 / 60 | `Attribute(JoinedStr)` | 5 | `f'AWS4{secret_key}'.encode` — `backend/services/uploads.py:164` |
| `dc0ac35c` | 425 / 60 | `Name` | 2 | `aggregation` — `backend/services/planungslauf.py:233` |
| `dc0ac35c` | 425 / 60 | `Attribute(Dict)` | 1 | `{…}.get` — `backend/main.py:65` |
| `87109723` | 114 / 0 | `Attribute(Call)` | 48 | `result.scalars().all` — `backend/repos/repositories.py:131` |
| `87109723` | 114 / 0 | `Attribute(Attribute)` | 30 | `uow.session.add` — `backend/services/customer_portal.py:169` |
| `87109723` | 114 / 0 | `Attribute(Name)` | 22 | `router.get` — `backend/api/routers/disposition.py:68` |
| `87109723` | 114 / 0 | `Attribute(Await)` | 12 | `(await uow.session.execute(select(MandantModel).where(MandantModel.id == mandant))).scalar_one` — `backend/services/customer_portal.py:64` |
| `87109723` | 114 / 0 | `Attribute(Subscript)` | 1 | `schritte[lauf_id].append` — `backend/repos/repositories.py:401` |
| `87109723` | 114 / 0 | `Name` | 1 | `callback` — `backend/services/planungslauf.py:358` |
| `6e251257` | 44 / 0 | `Attribute(Name)` | 20 | `session.add` — `backend/services/mobile_sync.py:168` |
| `6e251257` | 44 / 0 | `Attribute(Call)` | 14 | `select(TerminModel).where` — `backend/services/mobile_sync.py:61` |
| `6e251257` | 44 / 0 | `Attribute(Attribute)` | 6 | `uow.session.execute` — `backend/services/mobile_sync.py:53` |
| `6e251257` | 44 / 0 | `Attribute(Await)` | 3 | `(await session.execute(select(EinsatzModel).w … insatzModel.id).limit(1))).scalar_one_or_none` — `backend/services/mobile_sync.py:149` |
| `6e251257` | 44 / 0 | `Attribute(Constant)` | 1 | `'\|'.join` — `backend/services/mobile_sync.py:81` |
| `165a7611` | 34 / 0 | `Name` | 16 | `cls` — `backend/orchestrator/models.py:98` |
| `165a7611` | 34 / 0 | `Attribute(Name)` | 12 | `values.get` — `backend/orchestrator/models.py:94` |
| `165a7611` | 34 / 0 | `Attribute(Call)` | 5 | `super().__init__` — `backend/orchestrator/executors.py:384` |
| `165a7611` | 34 / 0 | `Attribute(Constant)` | 1 | `'\x1f'.join` — `backend/orchestrator/taskiq_adapter.py:136` |
| `5688e298` | 1 / 0 | `Attribute(Name)` | 1 | `object.__setattr__` — `backend/ports/api_application.py:52` |
| `4859da27` | 16 / 0 | `Attribute(Call)` | 11 | `select(ProcessStepModel).where` — `backend/repos/repositories.py:434` |
| `4859da27` | 16 / 0 | `Attribute(Name)` | 5 | `error.strip` — `backend/repos/repositories.py:513` |
| `10aae8a5` | 4 / 1 | `Attribute(Name)` | 4 | `datum.weekday` — `backend/services/planungslauf.py:102` |
| `9318f51c` | 2 / 0 | `Attribute(Name)` | 2 | `application.exception_handler` — `backend/main.py:25` |
| `23e12d8d` | 21 / 0 | `Attribute(Name)` | 14 | `route.sort` — `backend/services/baseline.py:231` |
| `23e12d8d` | 21 / 0 | `Attribute(Call)` | 3 | `_routen(termine).items` — `backend/services/baseline.py:113` |
| `23e12d8d` | 21 / 0 | `Attribute(Subscript)` | 3 | `result[termin.datum].append` — `backend/services/baseline.py:175` |
| `23e12d8d` | 21 / 0 | `Attribute(JoinedStr)` | 1 | `f'{typ.value}\|{datum.isoformat()}\|{ausgeloest_von}'.encode` — `backend/services/stoerung.py:75` |
| `266c4442` | 64 / 0 | `Attribute(Call)` | 41 | `result.scalars().all` — `backend/repos/repositories.py:83` |
| `266c4442` | 64 / 0 | `Attribute(Name)` | 22 | `raw.strip` — `backend/repos/mappers.py:69` |
| `266c4442` | 64 / 0 | `Attribute(Subscript)` | 1 | `objekt_ids[relation.gebiet_id].append` — `backend/repos/repositories.py:129` |
| `a0400c57` | 35 / 0 | `Attribute(Name)` | 31 | `route.append` — `backend/solver/daily_tour.py:173` |
| `a0400c57` | 35 / 0 | `Attribute(JoinedStr)` | 2 | `f'{_PROFILE}:{_VERSION}:'.encode` — `backend/geo/matrix.py:97` |
| `a0400c57` | 35 / 0 | `Attribute(Subscript)` | 1 | `zuordnungen[mitarbeiter_wert].append` — `backend/geo/clustering.py:152` |
| `a0400c57` | 35 / 0 | `Attribute(Constant)` | 1 | `','.join` — `backend/geo/clustering.py:189` |

FACT — Aggregate: 1030 added, 61 removed, net +969. Patterns: `Attribute(Call)` 405; `Attribute(Name)` 371; `Attribute(Await)` 118; `Attribute(Attribute)` 90; `Name` 21; `Attribute(Subscript)` 8; `Attribute(Constant)` 8; `Attribute(JoinedStr)` 8; `Attribute(Dict)` 1.

#### EE: additions

| FACT: SHA | Added / removed | Pattern | Count | Target excerpt + file:line at that SHA |
|---|---:|---|---:|---|
| `4657a666` | 2 / 0 | `Attribute(Name)` | 1 | `raw_type.strip` — `datamimic_ee/model/nested_key_model.py:295` |
| `4657a666` | 2 / 0 | `Attribute(Attribute)` | 1 | `child.text.strip` — `datamimic_ee/parsers/setup_parser.py:43` |
| `12a82eed` | 1 / 0 | `Attribute(Call)` | 1 | `logging.getLogger(__name__).exception` — `datamimic_ee/logger/__init__.py:82` |
| `027d880b` | 2 / 0 | `Attribute(Name)` | 2 | `get_settings.cache_clear` — `datamimic_ee/config.py:83` |
| `981f34e3` | 1 / 0 | `Attribute(Name)` | 1 | `normalized.isdigit` — `datamimic_ee/authoring/adapters/dm_json_codec.py:503` |

FACT — Aggregate: 6 added, 0 removed, net +6. Patterns: `Attribute(Name)` 4; `Attribute(Attribute)` 1; `Attribute(Call)` 1.

### Counterfactual options, not recommendations

HYPOTHESIS — Option b uses an explicit conservative syntax proxy pending a policy definition: exclude only immediate receivers `Constant`, `JoinedStr`, `Dict`, `Set`, `List`, and `Tuple`; these are builtin literal receivers. Keep all other unresolved records as potentially internal. Recompute both unresolved count and ratio with that numerator and the original `calls_total`. This does not identify every external target.

HYPOTHESIS — Option c below assumes every observed increase in both absolute unresolved and its ratio could be declared and was declared. If only the absolute increase were declarable, c would have the same numbers as a. Other scalar checks remain unchanged in all options.

| Conditional calculation | Repo #2 rejected / 16 | EE rejected / 10 |
|---|---:|---:|
| a: keep ratio, remove absolute unresolved gate | 9 | 6 |
| b: potentially internal using the stated literal exclusion | 12 | 6 |
| c: declare all absolute and ratio increases | 7 | 2 |
| d: unchanged checks before any new acceptance | 12 | 6 |

FACT — Repo #2's UNKNOWN pair stays UNKNOWN under every option. These values are recomputations of this sample, not implemented policy or full-check pass rates. `pledge accept` is currently a placeholder returning Exit 2 (`src/pledge/accept/__init__.py:9–20`); a new accept was neither executed nor treated as an existing bypass.

### Coverage, failures, and evidence limits

FACT — Repo #2: 23 report invocations, 22 Exit 0, one Exit 2. All 22 valid reports have no Diagnostics; the failed parent is `dd391df2` for candidate `b5ba2765`. Diagnostic: `kind=parse_error`, `subject=pledge.toml` (archive prefix omitted), `unknown_claim="The report result cannot be established: scan root is not a directory: backend"`, `remedy="Repair the reported input or execution failure and retry."` The source and producer were not fixed.

FACT — EE closure replay: 13 report invocations, all Exit 0, no Diagnostics, retries, or incomplete invocations. The first report took 14.127801 seconds, below 180 seconds; the median was 13.99858525 seconds. [The replay evidence](evidence/5d-ee-replay.json) records every source SHA, start/end timestamp, duration, process/result exit, source/report/result digest, and call count. It pins the checker, producer, and Python version and gives the report command.

FACT — One executor ran reports sequentially against fresh archives. Each invocation used exclusive output files and a durable start/end journal pair; all 13 pairs and result hashes matched. Scoped sources, producer files, contracts, runtime requirements, and contract provenance were verified against their Git blobs. All 13 reports are byte-identical to the previous valid reports; all 13 decoded classification ledgers and all 10 comparison results are identical. The comparison, addition-pattern, and option tables therefore remain unchanged: 6/10 EE pairs rejected.

FACT — The replay supersedes the initial EE run as the complete attempt record for 5d. The initial run retains two setup failures for `df869a07`: both Exit 2, `kind=parse_error`, `subject=producer` (archive prefix omitted), `unknown_claim` ends in the following contract errors; remedy for both is `"Repair the producer failure and run report again."`

- `CAP-LANGUAGE-AUTHORING: missing provenance files: docs/architecture/03-component-architecture.md` (0.455229415994836 seconds).
- `COMP-PARSERS: missing provenance files: AGENTS.md` (0.2569893750041956 seconds).

FACT — Those failures came from omitted files in temporary archives. Terra expanded archive inputs to the unchanged versioned provenance files; no source, contract, or producer code was changed.

UNKNOWN — The initial EE run's exact invocation count and one setup Diagnostic remain unrecoverable: overlapping temporary runner sessions reused filenames for `c799b024`. Retained process metadata says Exit 2 / 0.10166962500079535 seconds, while its associated result says Exit 0 and has no Diagnostics. Their pairing is invalid. That attempt is excluded from final comparisons and timings; its original Exit-2 JSON is unavailable. A later complete report for that SHA is independently source-verified. The retained evidence contains 16 complete result files and one unmatched Exit-2 metadata record; this does not establish an exact invocation count.

FACT — Repo #2 retains its original 23-invocation record and 0.497853-second median; it was not rerun for this closure. EE timing above covers all 13 replay invocations. The replay does not recover the missing initial-run evidence; no total or median combining both EE runs is claimed.

UNKNOWN — Whether each rejected feature is architecturally acceptable, and which policy change is right. Commit subjects describe changes but do not prove correctness. No policy was changed; no full check, accept, lock write, producer fix, rename, Rich CLI, or EE migration was performed.

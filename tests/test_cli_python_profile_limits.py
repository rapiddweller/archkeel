# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-644: a profile limit holds only what reads the part that it limits, through the release core.

Consumer: a CI job that reads the row of each rule. The Python collector decides no
unread constructs and measures no `private_crossings` budget. Each such limit
keeps its own rule (or, for a budget, the run) UNKNOWN; the rules on the import edges and the
files decide. A violation that the scan sees stays FAIL, and a hidden construct never passes:
Python runs the truth of each plant.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from test_cli_native_python_imports import RULE, project, rows, verdict
from test_cli_python_gap_effects import FILES, RULES

CONSTRUCT = {
    **RULE,
    "id": "NO-GETATTR",
    "kind": "forbidden_construct",
    "source": "app",
    "constructs": ["getattr"],
    "allowed_sources": [],
    "exact_sources": [],
}
UNREAD_CONSTRUCT = {**CONSTRUCT, "id": "NO-SETATTR", "constructs": ["setattr"]}
PLACEMENT = {
    **RULE,
    "id": "PROTOCOLS-IN-SERVICE",
    "kind": "symbol_placement",
    "source": "app",
    "class_kinds": ["protocol"],
    "allowed_sources": ["app.service"],
}
BUDGET = {"name": "private_crossings", "provenance": ["p"]}
# Prints `True` when `app.client.page` really calls the builtin `getattr` (the hidden construct).
CALLS_GETATTR = (
    "import ast, pathlib; tree = ast.parse(pathlib.Path('src/app/client/page.py').read_text()); "
    "print(any(isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'getattr' "
    "for n in ast.walk(tree)))"
)
# Prints `True` when importing `app.client.page` loads `app.service.secret` (the seen violation).
LOADS_SECRET = "import sys, app.client.page; print('app.service.secret' in sys.modules)"


class Plant(NamedTuple):
    files: dict[str, str]
    # The limited rules that the contract adds, and its measurement budgets.
    extra: list[dict[str, Any]]
    budgets: list[dict[str, Any]]
    # The rows that are not PASS, with their status. Each other rule is PASS.
    open: dict[str, str]
    # The text that the row of each held rule names.
    why: dict[str, str]
    # Python code that prints `True` when the hidden or seen fact is real.
    truth: str = ""


GETATTR_PAGE = "import app.service.model as model\nVALUE = getattr(model, 'VALUE')\n"
PLANTS = {
    # Before AD-644 the construct limit held every rule of the run.
    "construct": Plant(
        {"src/app/client/page.py": GETATTR_PAGE},
        [CONSTRUCT, UNREAD_CONSTRUCT],
        [],
        {"NO-GETATTR": "FAIL", "NO-SETATTR": "UNKNOWN"},
        {"NO-SETATTR": "the collector examines no setattr"},
        truth=CALLS_GETATTR,
    ),
    "construct beside a seen violation": Plant(
        {"src/app/client/page.py": "import app.service.secret\n" + GETATTR_PAGE},
        [CONSTRUCT, UNREAD_CONSTRUCT],
        [],
        {"NO-GETATTR": "FAIL", "NO-SETATTR": "UNKNOWN", "CLIENT-NO-SECRET": "FAIL"},
        {"NO-SETATTR": "the collector examines no setattr"},
        truth=LOADS_SECRET,
    ),
    # A proven empty class inventory lets placement and the edge rules pass.
    "symbol placement": Plant({}, [PLACEMENT], [], {}, {}),
    # A budget that no profile measures holds the run, and no rule.
    "budget": Plant({}, [], [BUDGET], {}, {}),
}


def scanned(binary: Path, root: Path, plant: Plant) -> dict[str, Any]:
    path = project(root, {**FILES, **plant.files}, contract_rules=[*RULES, *plant.extra])
    if plant.budgets:
        contract_path = path / "architecture-contract.json"
        contract = json.loads(contract_path.read_text())
        contract["declarations"] = {"measurement_budgets": plant.budgets}
        contract_path.write_text(json.dumps(contract))
    return verdict(binary, path)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_profile_limit_holds_only_what_reads_it(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    plant = PLANTS[name]
    result = scanned(release_core, tmp_path, plant)
    frame = result["frame"]
    decided = [rule["id"] for rule in [*RULES, *plant.extra]]
    expected = {rule: plant.open.get(rule, "PASS") for rule in decided}
    assert rows(result) == expected, frame["explained"]
    for rule, text in plant.why.items():
        assert text in frame["explained"][rule], frame["explained"][rule]
    # A limited part never lets the run pass.
    expected_status = (
        "PASS"
        if name == "symbol placement"
        else ("FAIL" if "FAIL" in plant.open.values() else "UNKNOWN")
    )
    assert result["status"] == expected_status, result
    if plant.truth:
        done = subprocess.run(
            [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, 'src'); {plant.truth}"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert done.stdout.strip() == "True", done


def test_placement_decides_and_an_unmeasured_budget_names_its_own_row(
    release_core: Path, tmp_path: Path
) -> None:
    placement = scanned(release_core, tmp_path / "placement", PLANTS["symbol placement"])
    assert rows(placement)["PROTOCOLS-IN-SERVICE"] == "PASS"
    budget = scanned(release_core, tmp_path / "budget", PLANTS["budget"])["frame"]
    assert "declarations.measurement_budgets.private_crossings" in budget["scope"], budget["scope"]


def test_the_python_collector_does_not_claim_a_nominal_selector_inventory(
    release_core: Path, tmp_path: Path
) -> None:
    rule = {
        **CONSTRUCT,
        "id": "NO-SELECTED-COMPARE",
        "constructs": ["string_literal_compare"],
        "selector": {
            "receiver": "app.client.page.Connection",
            "member": "state",
            "role": "equality",
            "literal": "forbidden",
        },
    }
    source = (
        "class Connection:\n    state = 'ready'\n"
        "def check(value: Connection):\n    return value.state == 'forbidden'\n"
    )
    root = project(
        tmp_path, {**FILES, "src/app/client/page.py": source}, contract_rules=[*RULES, rule]
    )
    contract = root / "architecture-contract.json"
    document = json.loads(contract.read_text())
    document["schema_version"] = "3.11.0"
    contract.write_text(json.dumps(document))
    result = verdict(release_core, root)
    assert rows(result)[rule["id"]] == "UNKNOWN"
    assert (
        "collector does not report a complete construct selector inventory"
        in result["frame"]["explained"][rule["id"]]
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def check():\n    assert False\n", "FAIL"),
        ("def check():\n    return True\n", "PASS"),
        ("exec('assert False')\n", "UNKNOWN"),
        ("from builtins import exec as run\nrun('assert False')\n", "UNKNOWN"),
    ],
)
def test_assert_construct_has_evidence_and_hidden_code_does_not_pass(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-ASSERT", "constructs": ["assert"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-ASSERT"] == expected, result["frame"]["explained"]
    if expected == "FAIL":
        frame = result["frame"]
        evidence = frame["details"]["NO-ASSERT"][0]["evidence"]
        assert [frame["locations"][item] for item in evidence] == [
            {"path": "src/app/client/page.py", "line": 2}
        ]


def test_assert_uses_its_function_owner_and_exact_line(release_core: Path, tmp_path: Path) -> None:
    rule = {
        **CONSTRUCT,
        "id": "NO-ASSERT",
        "source": "app.client.page",
        "constructs": ["assert"],
        "allowed_sources": ["app.client.page.Allowed"],
    }
    source = (
        "class Allowed:\n"
        "    def check(self):\n"
        "        assert True\n"
        "class Forbidden:\n"
        "    def check(self):\n"
        "        assert False\n"
    )
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-ASSERT"] == "FAIL"
    frame = json.dumps(result["frame"])
    assert "app.client.page.Forbidden.check" in frame
    assert "app.client.page.Allowed.check" not in frame
    details = result["frame"]["details"]["NO-ASSERT"]
    evidence = details[0]["evidence"]
    assert [result["frame"]["locations"][item] for item in evidence] == [
        {"path": "src/app/client/page.py", "line": 6}
    ]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("try:\n    pass\nexcept:\n    pass\n", "FAIL"),
        ("try:\n    pass\nexcept Exception:\n    pass\n", "FAIL"),
        ("try:\n    pass\nexcept (ValueError, Exception):\n    pass\n", "FAIL"),
        ("def check():\n    return True\n", "PASS"),
        ("E = Exception\ntry:\n    pass\nexcept E:\n    pass\n", "UNKNOWN"),
        ("try:\n    pass\nexcept ValueError:\n    pass\n", "UNKNOWN"),
        ("Exception = ValueError\ntry:\n    pass\nexcept Exception:\n    pass\n", "UNKNOWN"),
        (
            "try:\n    pass\nexcept ValueError:\n    pass\ntry:\n    pass\nexcept:\n    pass\n",
            "FAIL",
        ),
    ],
)
def test_broad_handler_is_proven_or_left_unknown(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-BROAD-EXCEPT", "constructs": ["broad_except"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-BROAD-EXCEPT"] == expected, result["frame"]["explained"]
    if expected == "UNKNOWN":
        assert (
            "construct absence is not completely observed"
            in result["frame"]["explained"]["NO-BROAD-EXCEPT"]
        )
    if expected == "FAIL":
        frame = result["frame"]
        evidence = frame["details"]["NO-BROAD-EXCEPT"][0]["evidence"]
        assert frame["locations"][evidence[0]]["path"] == "src/app/client/page.py"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("value = item.__dict__\n", "FAIL"),
        ("value = item.__dict__.__dict__\n", "FAIL"),
        ("value = item.__dict__.key.__dict__\n", "FAIL"),
        ("value = 1\n", "PASS"),
        ("value = getattr(item, '__dict__')\n", "UNKNOWN"),
        ("value = item.__getattribute__('__' + 'dict__')\n", "UNKNOWN"),
        ("f = getattr\nvalue = f(item, name)\n", "UNKNOWN"),
        ("value = item.__dict__\nother = f(item)\n", "FAIL"),
    ],
)
def test_dunder_dict_is_proven_or_left_unknown(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-DICT", "constructs": ["dunder_dict"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-DICT"] == expected, result["frame"]["explained"]
    if expected == "UNKNOWN":
        assert (
            "construct absence is not completely observed"
            in result["frame"]["explained"]["NO-DICT"]
        )
    if expected == "FAIL":
        frame = result["frame"]
        evidence = frame["details"]["NO-DICT"][0]["evidence"]
        assert frame["locations"][evidence[0]] == {"path": "src/app/client/page.py", "line": 1}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("value = vars(item)\n", "FAIL"),
        ("value = 1\n", "PASS"),
        ("f = vars\nvalue = f(item)\n", "UNKNOWN"),
        ("f = vars\n", "UNKNOWN"),
        ("vars = other\nvalue = vars(item)\n", "UNKNOWN"),
        ("value = f(item)\n", "UNKNOWN"),
        ("value = vars(item)\nother = f(item)\n", "FAIL"),
    ],
)
def test_vars_call_is_proven_or_left_unknown(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-VARS", "constructs": ["vars"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-VARS"] == expected, result["frame"]["explained"]
    if expected == "UNKNOWN":
        assert (
            "construct absence is not completely observed"
            in result["frame"]["explained"]["NO-VARS"]
        )
    if expected == "FAIL":
        frame = result["frame"]
        evidence = frame["details"]["NO-VARS"][0]["evidence"]
        assert frame["locations"][evidence[0]] == {"path": "src/app/client/page.py", "line": 1}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("value = item == 'ready'\n", "FAIL"),
        ("value = b'ready' != item\n", "FAIL"),
        ("value = low < item == 'ready'\n", "FAIL"),
        ("value = 1\n", "PASS"),
        ("READY = 'ready'\nvalue = item == READY\n", "UNKNOWN"),
        ("value = item in ('ready', 'done')\n", "UNKNOWN"),
        ("value = item.startswith('ready')\n", "UNKNOWN"),
        ("predicate = item.startswith\n", "UNKNOWN"),
        ("match item:\n    case 'ready': pass\n", "UNKNOWN"),
    ],
)
def test_literal_comparison_is_proven_or_left_unknown(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-STRING-COMPARE", "constructs": ["string_literal_compare"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-STRING-COMPARE"] == expected, result["frame"]["explained"]
    if expected == "UNKNOWN":
        assert (
            "construct absence is not completely observed"
            in result["frame"]["explained"]["NO-STRING-COMPARE"]
        )
    if expected == "FAIL":
        frame = result["frame"]
        evidence = frame["details"]["NO-STRING-COMPARE"][0]["evidence"]
        assert frame["locations"][evidence[0]] == {"path": "src/app/client/page.py", "line": 1}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("value = getattr(item, 'name')\n", "FAIL"),
        ("value = 1\n", "PASS"),
        ("f = getattr\nvalue = f(item, 'name')\n", "UNKNOWN"),
        ("f = getattr\n", "UNKNOWN"),
        ("getattr = other\nvalue = getattr(item, 'name')\n", "UNKNOWN"),
        ("value = f(item, 'name')\n", "UNKNOWN"),
        ("value = getattr(item, 'name')\nother = f(item)\n", "FAIL"),
    ],
)
def test_getattr_call_is_proven_or_left_unknown(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-GETATTR", "constructs": ["getattr"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-GETATTR"] == expected, result["frame"]["explained"]
    if expected == "UNKNOWN":
        assert (
            "construct absence is not completely observed"
            in result["frame"]["explained"]["NO-GETATTR"]
        )
    if expected == "FAIL":
        frame = result["frame"]
        evidence = frame["details"]["NO-GETATTR"][0]["evidence"]
        assert frame["locations"][evidence[0]] == {"path": "src/app/client/page.py", "line": 1}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from typing import Any\nx: Any = None\n", "FAIL"),
        ("import typing\ndef f(x: typing.Any): pass\n", "FAIL"),
        ("from typing import Any\ndef f() -> list[Any]: pass\n", "FAIL"),
        ("from typing import Any\nx = Any\n", "UNKNOWN"),
        ("from typing import Any as Opaque\nx: Opaque = None\n", "UNKNOWN"),
        ("x: 'Any' = None\n", "UNKNOWN"),
        ("class Any: pass\nx: Any = None\n", "UNKNOWN"),
        ("Any = object\nx: Any = None\n", "UNKNOWN"),
        ("from typing import Any\nclass Any: pass\nx: Any = None\n", "UNKNOWN"),
        ("from typing import Any\ndef f():\n    Any = 1\nx: Any = None\n", "UNKNOWN"),
        ("from typing import *\nx: Any = None\n", "FAIL"),
        ("if TYPE_CHECKING:\n    from typing import Any\nx: Any = None\n", "FAIL"),
    ],
)
def test_opaque_annotations_are_reported_or_left_unknown(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-ANY", "constructs": ["any_annotation"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-ANY"] == expected, result["frame"]["explained"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("value = __import__('os')\n", "FAIL"),
        ("value = __import__(name)\n", "FAIL"),
        ("from importlib import import_module\nvalue = import_module('os')\n", "FAIL"),
        ("import importlib as lib\nvalue = lib.import_module('os')\n", "FAIL"),
        ("from importlib import import_module as load\nvalue = load(name)\n", "FAIL"),
        ("loader = __import__\nvalue = loader(name)\n", "UNKNOWN"),
        ("__import__ = other\nvalue = __import__(name)\n", "UNKNOWN"),
        (
            "from importlib import import_module\n"
            "import_module = other\nvalue = import_module(name)\n",
            "UNKNOWN",
        ),
        ("value = 1\n", "UNKNOWN"),
    ],
)
def test_dynamic_import_is_reported_or_left_unknown(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-DYNAMIC", "constructs": ["dynamic_import"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-DYNAMIC"] == expected, result["frame"]["explained"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from typing import cast\nvalue = cast(int, obj)\n", "FAIL"),
        ("import typing as t\nvalue = t.cast(int, obj)\n", "FAIL"),
        ("from typing_extensions import cast as c\nvalue = c(int, obj)\n", "FAIL"),
        ("from typing import cast\ncast = other\nvalue = cast(int, obj)\n", "UNKNOWN"),
        ("value = other(int, obj)\n", "UNKNOWN"),
    ],
)
def test_cast_is_reported_or_left_unknown(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    rule = {**CONSTRUCT, "id": "NO-CAST", "constructs": ["cast"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-CAST"] == expected, result["frame"]["explained"]

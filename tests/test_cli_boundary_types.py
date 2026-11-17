# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-550: the core decides the syntax half of `boundary_types` on plants.

`boundary_types_rows.json` pins, for each plant of `boundary_types_plants.py`, the row of release
4.0.1 (`validate --json` of an installed 4.0.1 on the same tree), the row of the core and the named
causes of its gaps. A core PASS needs the truth PASS and a core FAIL needs the truth FAIL. The core
never answers PASS where the release answers FAIL or UNKNOWN. Every other difference from the
release is a stricter UNKNOWN: a named gap where the release decides.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from boundary_types_plants import PLANTS, Plant, facade
from boundary_types_sources import RULE, project
from test_cli_core_only_scan import command

ROWS = json.loads((Path(__file__).parent / "boundary_types_rows.json").read_text())
STRICTER = {("PASS", "UNKNOWN"), ("FAIL", "UNKNOWN")}
# (equal, PASS to UNKNOWN, FAIL to UNKNOWN, plants) between release 4.0.1 and the core.
CAUSE = re.compile(r"boundary_type_position: \S+ \S+: (\w+): ")


def use_standard_library_premise(root: Path) -> None:
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = "3.17.0"
    contract["declarations"] = {
        "premises": [
            {
                "id": "P-STD",
                "name": "standard_library_unchanged",
                "rationale": "The standard library is unchanged.",
                "provenance": ["project policy"],
            }
        ]
    }
    path.write_text(json.dumps(contract))


@pytest.mark.parametrize(
    ("model", "expected", "reason"),
    [
        (
            "from dataclasses import dataclass\n"
            "@dataclass\nclass Amount:\n    cents: int\n"
            "@dataclass\nclass Order:\n    amount: Amount\n"
            "__all__ = ['Amount', 'Order']\n",
            "PASS",
            None,
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\nclass Order:\n    values: dict[str, int]\n"
            "__all__ = ['Order']\n",
            "FAIL",
            None,
        ),
        (
            "from dataclasses import dataclass\nfrom typing import Optional\n"
            "@dataclass\nclass Order:\n    values: Optional[dict]\n"
            "__all__ = ['Order']\n",
            "FAIL",
            None,
        ),
        (
            "from dataclasses import dataclass, field\n"
            "@dataclass\nclass Order:\n    value: int = field(init=False)\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "field_walk",
        ),
        (
            "from dataclasses import dataclass\nfrom typing import ClassVar\n"
            "@dataclass\nclass Order:\n    value: ClassVar[int] = 1\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "field_walk",
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\nclass Order:\n    value: NotScanned\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "unresolved_name",
        ),
        (
            "from dataclasses import dataclass\nfrom typing import Protocol\n"
            "class Sender(Protocol):\n    def send(self) -> None: ...\n"
            "@dataclass\nclass Order:\n    sender: Sender\n"
            "__all__ = ['Order', 'Sender']\n",
            "UNKNOWN",
            None,
        ),
        (
            "def custom(cls):\n    return cls\n"
            "@custom\nclass Order:\n    value: int\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "unresolved_name",
        ),
        (
            "import dataclasses\n"
            "def replace(cls):\n    return cls\n"
            "dataclasses.dataclass = replace\n"
            "@dataclasses.dataclass\nclass Order:\n    value: int\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "unresolved_name",
        ),
        (
            "import typing\nfrom typing import Optional\n"
            "typing.Optional = dict\n"
            "from dataclasses import dataclass\n"
            "@dataclass\nclass Order:\n    value: Optional[int]\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "unresolved_name",
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\nclass Order:\n    value: int\n"
            "Order.value = dict\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "unresolved_name",
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\nclass Order:\n    value: int\n"
            "vars(Order)['value'] = dict\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "unresolved_name",
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\nclass Order:\n    value: int\n"
            "Order.__annotations__['value'] = dict\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "unresolved_name",
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\nclass Order:\n    value: int\n"
            "Order.__dataclass_fields__['value'].type = dict\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "unresolved_name",
        ),
        (
            "from dataclasses import dataclass\n"
            "@dataclass\nclass Order:\n    child: Order | None\n"
            "__all__ = ['Order']\n",
            "UNKNOWN",
            "recursive dataclass field walk",
        ),
    ],
)
def test_dataclass_return_walk_is_bounded_by_proven_field_shapes(
    release_core: Path,
    tmp_path: Path,
    model: str,
    expected: str,
    reason: str | None,
) -> None:
    plant = Plant(
        facade(
            "def place() -> Order:\n    raise NotImplementedError\n",
            "'place'",
            "from app.model import Order\n",
        ),
        "PASS",
        {"model.py": model},
        public=("app.api", "app.model"),
    )
    root = project(tmp_path / "p", plant)
    use_standard_library_premise(root)
    result = json.loads(command(release_core, root, "--json").stdout)
    assert result["frame"]["rules"][RULE] == ["boundary_types", expected], result
    if reason:
        assert reason in json.dumps(result), result


def test_f_architecture_dataclass_return_pass_names_its_premise(
    release_core: Path,
) -> None:
    root = Path(__file__).parents[1] / "fixtures/F-architecture"
    result = json.loads(command(release_core, root, "--json", verb="report").stdout)
    assert result["frame"]["rules"]["APP-TYPES-NOT-DICT"] == ["boundary_types", "PASS"]
    premises = result["frame"]["premises"]["APP-TYPES-NOT-DICT"]
    assert any(
        item["kind"] == "standard_library_unchanged"
        and item["subject"] == "shop.app.orders.place_order:return"
        for item in premises
    )


def test_dataclass_return_without_the_premise_stays_unknown(
    release_core: Path, tmp_path: Path
) -> None:
    plant = Plant(
        facade(
            "def place() -> Order:\n    raise NotImplementedError\n",
            "'place'",
            "from app.model import Order\n",
        ),
        "PASS",
        {
            "model.py": (
                "from dataclasses import dataclass\n"
                "@dataclass\nclass Order:\n    value: int\n"
                "__all__ = ['Order']\n"
            )
        },
        public=("app.api", "app.model"),
    )
    result = json.loads(command(release_core, project(tmp_path / "p", plant), "--json").stdout)
    assert result["frame"]["rules"][RULE] == ["boundary_types", "UNKNOWN"], result
    assert "standard_library_unchanged" in json.dumps(result["frame"])


def test_dataclass_field_writer_outside_scan_roots_stays_unknown(
    release_core: Path, tmp_path: Path
) -> None:
    plant = Plant(
        facade(
            "def place() -> Order:\n    raise NotImplementedError\n",
            "'place'",
            "import startup_plugin\nfrom app.model import Order\n",
        ),
        "PASS",
        {
            "model.py": (
                "from dataclasses import dataclass\n"
                "@dataclass\nclass Order:\n    value: int\n"
                "__all__ = ['Order']\n"
            )
        },
        public=("app.api", "app.model"),
    )
    root = project(tmp_path / "p", plant)
    (root / "startup_plugin.py").write_text("from app.model import Order\nOrder.value = dict\n")
    use_standard_library_premise(root)
    result = json.loads(command(release_core, root, "--json").stdout)
    assert result["frame"]["rules"][RULE] == ["boundary_types", "UNKNOWN"], result
    assert "may change a dataclass field" in json.dumps(result)


def test_every_plant_has_a_pinned_row() -> None:
    assert set(ROWS) == set(PLANTS)


@pytest.mark.parametrize(
    ("imports", "annotation"),
    [("from pathlib import Path\n", "Path"), ("import pathlib\n", "pathlib.Path")],
)
def test_a_standard_library_type_without_a_premise_is_unknown(
    release_core: Path, tmp_path: Path, imports: str, annotation: str
) -> None:
    plant = Plant(facade(f"def f(a: {annotation}) -> int:\n    return 1\n", "'f'", imports), "PASS")
    result = json.loads(command(release_core, project(tmp_path / "p", plant), "--json").stdout)
    assert result["frame"]["rules"][RULE] == ["boundary_types", "UNKNOWN"], result
    assert "standard_library_unchanged" in json.dumps(result["frame"])


def test_a_standard_library_type_with_a_premise_passes_assuming(
    release_core: Path, tmp_path: Path
) -> None:
    plant = Plant(
        facade("def f(a: Path) -> int:\n    return 1\n", "'f'", "from pathlib import Path\n"),
        "PASS",
    )
    root = project(tmp_path / "p", plant)
    use_standard_library_premise(root)
    result = json.loads(command(release_core, root, "--json").stdout)
    assert "refusal" not in result, result
    assert RULE in result["frame"]["rules"], result
    assert result["frame"]["rules"][RULE] == ["boundary_types", "PASS"], result
    assert "standard_library_unchanged" in json.dumps(result["frame"]["premises"])


@pytest.mark.parametrize(
    "write",
    [
        "pathlib.Path = dict",
        "setattr(pathlib, 'Path', dict)",
        "vars(pathlib)['Path'] = dict",
        "pathlib.__dict__['Path'] = dict",
        "sys.modules['pathlib'] = pathlib",
    ],
)
def test_a_changed_standard_library_type_does_not_pass(
    release_core: Path, tmp_path: Path, write: str
) -> None:
    imports = f"import pathlib\nimport sys\n{write}\nfrom pathlib import Path\n"
    plant = Plant(facade("def f(a: Path) -> int:\n    return 1\n", "'f'", imports), "FAIL")
    root = project(tmp_path / "p", plant)
    use_standard_library_premise(root)
    result = json.loads(command(release_core, root, "--json").stdout)
    assert result["frame"]["rules"][RULE] == ["boundary_types", "UNKNOWN"], result


@pytest.mark.parametrize("premise", [False, True])
def test_a_repository_writer_outside_the_scan_roots_keeps_the_type_unknown(
    release_core: Path, tmp_path: Path, premise: bool
) -> None:
    """The premise covers code outside the repository only: a file of the repository outside the
    scan roots that writes `pathlib.Path` keeps the type UNKNOWN, with or without the premise."""
    imports = "import startup_plugin\nfrom pathlib import Path\n"
    plant = Plant(facade("def f(a: Path) -> int:\n    return 1\n", "'f'", imports), "FAIL")
    root = project(tmp_path / "p", plant)
    (root / "startup_plugin.py").write_text("import pathlib\npathlib.Path = dict\n")
    if premise:
        use_standard_library_premise(root)
    result = json.loads(command(release_core, root, "--json").stdout)
    assert result["frame"]["rules"][RULE] == ["boundary_types", "UNKNOWN"], result
    assert "may change the standard library name pathlib.Path" in json.dumps(result["frame"])


@pytest.mark.parametrize(("premise", "expected"), [(False, "UNKNOWN"), (True, "PASS")])
def test_contextmanager_needs_the_standard_library_premise(
    release_core: Path, tmp_path: Path, premise: bool, expected: str
) -> None:
    imports = "from contextlib import contextmanager\nfrom typing import Iterator\n"
    plant = Plant(
        facade("@contextmanager\ndef f(a: int) -> Iterator[int]:\n    yield a\n", "'f'", imports),
        "PASS",
    )
    root = project(tmp_path / "p", plant)
    if premise:
        use_standard_library_premise(root)
    result = json.loads(command(release_core, root, "--json").stdout)
    assert result["frame"]["rules"][RULE] == ["boundary_types", expected], result


def test_wraps_with_different_signatures_stays_unknown(release_core: Path, tmp_path: Path) -> None:
    body = (
        "def original(a: dict) -> dict:\n    return a\n"
        "@wraps(original)\ndef f(a: int) -> int:\n    return a\n"
    )
    root = project(
        tmp_path / "p", Plant(facade(body, "'f'", "from functools import wraps\n"), "OPEN")
    )
    use_standard_library_premise(root)
    result = json.loads(command(release_core, root, "--json").stdout)
    assert result["frame"]["rules"][RULE] == ["boundary_types", "UNKNOWN"], result
    assert "wrapper and the wrapped function expose different signatures" in json.dumps(result)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_core_row_is_sound_and_never_weaker_than_the_release(name: str) -> None:
    four, core, _ = ROWS[name]
    truth = PLANTS[name].truth
    assert four == core or (four, core) in STRICTER
    assert core != "PASS" or truth == "PASS"
    assert core != "FAIL" or truth == "FAIL"


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_rule_row_is_the_pinned_row(release_core: Path, tmp_path: Path, name: str) -> None:
    _, expected, cause = ROWS[name]
    root = project(tmp_path / "p", PLANTS[name])
    result = json.loads(command(release_core, root, "--json").stdout)
    assert "refusal" not in result, result
    assert result["frame"]["rules"][RULE] == ["boundary_types", expected], result["frame"]
    # The causes are machine words: the JSON keeps them, the text puts them in plain words (#1319).
    frame = result["frame"]
    rows = [gap["reason"] for gap in result["gaps"]] + list(frame["explained"].values())
    rows += [row["cause"] for found in frame["details"].values() for row in found]
    text = "\n".join(rows)
    found = {match.group(1) for line in text.splitlines() if (match := CAUSE.search(line))}
    if "boundary_type_allowance_stale:" in text:
        found.add("stale_allowance")
    assert "; ".join(sorted(found)) == cause
    if expected == "FAIL":
        assert result["exit_code"] == 1

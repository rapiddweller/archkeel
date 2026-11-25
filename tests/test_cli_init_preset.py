# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1987 (AD-1087): `init --preset layered` and `--preset hexagonal` draft rules of existing kinds.

The plant is the `shop` layout of `fixtures/F-architecture`. The fixture has no top-level
`__init__.py`, which `init` needs, so the plant adds an empty one.
"""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from archkeel.cli import core_only
from archkeel.cli.init_draft import draft

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures/F-architecture"
SCHEMA = ROOT / "schema/architecture-contract-3.14.schema.json"
GIT = ["git", "-c", "user.email=a@b", "-c", "user.name=a"]
# The outermost layer first, as the user writes it.
LAYERED = ("--preset", "layered", "--layers", "cli,render,app,store,model")
HEXAGONAL = ("--preset", "hexagonal", "--layers", "app,model", "--adapters", "store,render")
# The bytes that `init` wrote on `main` for this plant, before presets existed.
DEFAULT_SHA256 = {
    "archkeel.toml": "cc9d0b5d85745ed77d6618c15eab2b8f0933e847d3df9fd617db97c8a4499dce",
    "architecture-contract.json": (
        "230f5135923ad886e531e169eb9e2e0e6dbb33440f2f6c349bb210b6919e6a48"
    ),
    "docs/architecture/architecture.md": (
        "edec798e50501ff12d63843aaba423d4e006302d37d35997f7da52329489e209"
    ),
}


def shop(root: Path) -> Path:
    shutil.copytree(FIXTURE / "shop", root / "shop")
    shutil.copy(FIXTURE / "pyproject.toml", root / "pyproject.toml")
    (root / "shop/__init__.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
    subprocess.run([*GIT, "commit", "-qm", "plant"], cwd=root, check=True)
    return root


def init(root: Path, *argv: str) -> int:
    return core_only.run(["init", "--root", str(root), "--json", *argv])


def contract(root: Path) -> dict[str, object]:
    return json.loads((root / "architecture-contract.json").read_text(encoding="utf-8"))


def rules(root: Path, kind: str) -> list[dict[str, object]]:
    found = contract(root)["rules"]
    assert isinstance(found, list)
    return [rule for rule in found if rule["kind"] == kind]


def verdict(capsys: pytest.CaptureFixture[str], root: Path) -> dict[str, object]:
    capsys.readouterr()
    core_only.run(["validate", "--root", str(root), "--json"])
    return json.loads(capsys.readouterr().out)


def test_the_layered_draft_passes_the_contract_schema(tmp_path: Path) -> None:
    """Acceptance 1: no schema error, for both presets."""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for index, preset in enumerate((LAYERED, HEXAGONAL)):
        root = shop(tmp_path / str(index))
        assert init(root, *preset) == 0
        assert list(Draft202012Validator(schema).iter_errors(contract(root))) == []


def test_the_draft_is_the_same_on_each_run(tmp_path: Path) -> None:
    """Acceptance 2."""
    first, second = shop(tmp_path / "a"), shop(tmp_path / "b")
    assert init(first, *LAYERED) == init(second, *LAYERED) == 0
    for name in DEFAULT_SHA256:
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_validate_gives_a_verdict_and_an_inner_import_of_an_outer_layer_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Acceptance 3, and the rule checks imports: `layer_order` alone checks `requires` only."""
    root = shop(tmp_path)
    assert init(root, *LAYERED) == 0
    first = verdict(capsys, root)
    assert first["status"] == "UNKNOWN" and "refusal" not in first
    path = root / "shop/model/entities.py"
    path.write_text(
        path.read_text(encoding="utf-8") + "import shop.render.text\n", encoding="utf-8"
    )
    second = verdict(capsys, root)
    assert second["status"] == "FAIL" and "refusal" not in second


def test_without_a_preset_the_draft_is_what_main_wrote(tmp_path: Path) -> None:
    """Acceptance 4."""
    root = shop(tmp_path)
    assert init(root) == 0
    written = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in DEFAULT_SHA256
    }
    assert written == DEFAULT_SHA256
    assert not any("layer" in component for component in contract(root)["components"])  # type: ignore[attr-defined]


def test_the_docs_show_each_preset_with_the_command_of_these_tests() -> None:
    """Acceptance 5."""
    text = (ROOT / "docs/onboarding.md").read_text(encoding="utf-8")
    assert "archkeel init " + " ".join(LAYERED) in text
    assert "archkeel init " + " ".join(HEXAGONAL) in text


def test_the_layers_run_from_the_outermost_and_the_rules_follow(tmp_path: Path) -> None:
    root = shop(tmp_path)
    assert init(root, *LAYERED) == 0
    (order,) = rules(root, "layer_order")
    assert order["layers"] == ["model", "store", "app", "render", "cli"]
    forbidden = {(r["source"], r["target"]) for r in rules(root, "forbidden_dependency")}
    assert len(forbidden) == 10 and ("shop.model", "shop.cli") in forbidden
    assert ("shop.cli", "shop.model") not in forbidden
    assert all(
        r["rationale"] and "TODO" not in str(r["rationale"]) for r in rules(root, "layer_order")
    )


def test_the_hexagonal_draft_isolates_the_adapters_and_keeps_the_core_apart(
    tmp_path: Path,
) -> None:
    root = shop(tmp_path)
    assert init(root, *HEXAGONAL) == 0
    (isolation,) = rules(root, "sibling_isolation")
    assert isolation["members"] == ["shop.store", "shop.render"]
    (order,) = rules(root, "layer_order")
    assert order["layers"] == ["model", "app", "adapters"]
    pairs = {(r["source"], r["target"]) for r in rules(root, "forbidden_dependency")}
    assert pairs == {
        ("shop.model", "shop.app"),
        ("shop.model", "shop.store"),
        ("shop.model", "shop.render"),
        ("shop.app", "shop.store"),
        ("shop.app", "shop.render"),
    }


@pytest.mark.parametrize(
    "argv",
    [
        ("--layers", "app,model"),
        ("--preset", "layered"),
        ("--preset", "layered", "--layers", "app"),
        ("--preset", "layered", "--layers", "app,model", "--adapters", "store,render"),
        ("--preset", "hexagonal", "--layers", "app", "--adapters", "store"),
        ("--preset", "layered", "--layers", "app,app"),
        ("--preset", "layered", "--layers", "app,missing"),
        ("--preset", "clean", "--layers", "app,model"),
    ],
)
def test_a_name_that_does_not_fit_refuses_the_draft_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]
) -> None:
    root = shop(tmp_path)
    assert init(root, *argv) == 2
    assert json.loads(capsys.readouterr().out)["refusal"]["kind"] == "invalid_input"
    assert not (root / "archkeel.toml").exists()


def test_a_preset_needs_one_language_area_for_the_draft(tmp_path: Path) -> None:
    root = shop(tmp_path)
    (root / "web/src").mkdir(parents=True)
    (root / "web/package.json").write_text('{"name": "web", "version": "1.0.0"}', "utf-8")
    (root / "web/tsconfig.json").write_text(
        '{"compilerOptions": {"strict": true, "noEmit": true}, "include": ["src/**/*.ts"]}', "utf-8"
    )
    (root / "web/src/index.ts").write_text("export const w = 1;\n", encoding="utf-8")
    assert draft(root).parts
    assert init(root, *LAYERED) == 2
    assert not (root / "archkeel.toml").exists()


def test_a_draft_can_name_the_layers_without_the_core(tmp_path: Path) -> None:
    """The component `root` stays outside the layers: `layer_order` lists only the named ones."""
    root = shop(tmp_path)
    assert init(root, "--preset", "layered", "--layers", "render,model") == 0
    (order,) = rules(root, "layer_order")
    assert order["components"] == ["model", "render"]

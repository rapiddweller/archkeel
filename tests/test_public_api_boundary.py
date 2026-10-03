# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Public API closure includes resolved signature types and inherited public fields.

Unproven inheritance retains UNKNOWN with source evidence (AD-73, AD-131).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_analyzer import _component, _observe

from archkeel.analyzer.embedded.records import classified
from archkeel.analyzer.embedded.violations import _public_api_symbol
from archkeel.analyzer.python.type_shapes import collect_type_shapes, symbol_type_expressions
from archkeel.check.validation import public_api_diagnostics
from archkeel.cli import main
from archkeel.ir.codec import decode_canonical_model, decode_json, parse_contract, parse_observation
from archkeel.ir.model import Diagnostic, EvidenceClass


def _prepare(tmp_path: Path, public_api: list[str], facade_source: str) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    contract = {
        "schema_version": "2.1.0",
        "components": [],
        "rules": [],
        "declarations": {"public_api": public_api},
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "facade.py").write_text(facade_source)
    return tmp_path


def _public_api_diagnostics(tmp_path: Path) -> tuple[Diagnostic, ...]:
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    contract = parse_contract(decode_json((tmp_path / "contract.json").read_bytes()))
    return public_api_diagnostics(contract, result.observation)


def _commit_public_api_fixture(tmp_path: Path, public: tuple[str, ...] = ()) -> None:
    contract = json.loads((tmp_path / "contract.json").read_text())
    component = _component("sample", packages=["sample"], public=list(public))
    component["provenance"] = ["probe.md"]
    contract["components"] = [component]
    contract["declarations"]["public_api_provenance"] = ["probe.md"]
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "probe.md").write_text(
        "<!-- archkeel-component-graph -->\n```mermaid\nflowchart TD\n    sample\n```\n"
    )
    (tmp_path / "archkeel.toml").write_text(
        '[scan]\nroots = ["sample"]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Demo",
            "-c",
            "user.email=demo@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(args, cwd=tmp_path, check=True, capture_output=True)


def test_public_api_rejects_duplicate_functions_regardless_of_record_order() -> None:
    for symbol_module, origins in (
        ("sample.facade", ()),
        ("sample.model", (("sample.model", "probe"),)),
    ):
        hidden = classified(
            item_id=f"SYM-{symbol_module}-hidden",
            evidence_class=EvidenceClass.FACT,
            area="repository_topology",
            kind="function",
            title="probe",
            data={"module": symbol_module, "name": "probe", "parent": None, "returns": "Hidden"},
        )
        scalar = classified(
            item_id=f"SYM-{symbol_module}-scalar",
            evidence_class=EvidenceClass.FACT,
            area="repository_topology",
            kind="function",
            title="probe",
            data={"module": symbol_module, "name": "probe", "parent": None, "returns": "str"},
        )
        assert (
            _public_api_symbol(
                [hidden, scalar],
                "sample.facade",
                "probe",
                origins,
                False,
                type_shapes=collect_type_shapes(symbol_type_expressions([hidden, scalar])),
            )
            is _public_api_symbol(
                [scalar, hidden],
                "sample.facade",
                "probe",
                origins,
                False,
                type_shapes=collect_type_shapes(symbol_type_expressions([scalar, hidden])),
            )
            is None
        )


def test_public_api_reports_a_declared_function_returning_an_undeclared_type(
    tmp_path: Path,
) -> None:
    """Only `make_config` is declared; `Config`, the type it hands out, is not."""
    _prepare(
        tmp_path,
        ["sample.facade:make_config"],
        "class Config:\n    pass\n\n\ndef make_config() -> Config:\n    return Config()\n",
    )

    diagnostics = _public_api_diagnostics(tmp_path)

    assert diagnostics != (), "a declared function returning an undeclared type must be reported"
    assert any("Config" in diagnostic.unknown_claim for diagnostic in diagnostics)


def test_public_api_reports_a_declared_function_taking_an_undeclared_type(tmp_path: Path) -> None:
    """The same leak on the side a consumer must supply rather than the side it receives."""
    _prepare(
        tmp_path,
        ["sample.facade:use_config"],
        "class Config:\n    pass\n\n\ndef use_config(config: Config) -> None:\n    return None\n",
    )

    diagnostics = _public_api_diagnostics(tmp_path)

    assert diagnostics != (), "a declared function taking an undeclared type must be reported"
    assert any("Config" in diagnostic.unknown_claim for diagnostic in diagnostics)


def test_public_api_reports_a_declared_classs_undeclared_attribute_type(tmp_path: Path) -> None:
    """AD-70's own example: `ViolationRow.fingerprint` is why `ViolationFingerprint` is declared
    at all. `Row` is declared here; `Fingerprint`, the type its own attribute hands out, is not
    -- a consumer holding a `Row` can reach `Fingerprint` with no promise covering it."""
    _prepare(
        tmp_path,
        ["sample.facade:Row"],
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Fingerprint:\n"
        "    value: str\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Row:\n"
        "    fingerprint: Fingerprint\n",
    )

    diagnostics = _public_api_diagnostics(tmp_path)

    assert diagnostics != (), "a declared class's undeclared attribute type must be reported"
    assert any("Fingerprint" in diagnostic.unknown_claim for diagnostic in diagnostics)


def test_public_api_inspects_a_local_class_whose_name_is_a_broad_type(tmp_path: Path) -> None:
    _prepare(
        tmp_path,
        ["sample.facade:Dict"],
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Hidden:\n"
        "    value: str\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Dict:\n"
        "    hidden: Hidden\n",
    )

    diagnostics = _public_api_diagnostics(tmp_path)

    assert diagnostics != (), "a local class named Dict must still expose its field types"
    assert any("Hidden" in diagnostic.unknown_claim for diagnostic in diagnostics)


def test_public_api_reports_a_reexported_classs_undeclared_attribute_type(
    tmp_path: Path,
) -> None:
    _prepare(
        tmp_path,
        ["sample.facade:Row"],
        "from sample.model import Row\n\n__all__ = ['Row']\n",
    )
    (tmp_path / "sample/model.py").write_text(
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Fingerprint:\n"
        "    value: str\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Row:\n"
        "    fingerprint: Fingerprint\n"
    )

    diagnostics = _public_api_diagnostics(tmp_path)

    assert diagnostics != (), "a re-exported class's undeclared field type must be reported"
    assert any("Fingerprint" in diagnostic.unknown_claim for diagnostic in diagnostics)


def test_public_api_reports_a_reexported_functions_undeclared_return_type(
    tmp_path: Path,
) -> None:
    _prepare(
        tmp_path,
        ["sample.facade:load"],
        "from sample.model import load\n\n__all__ = ['load']\n",
    )
    (tmp_path / "sample/model.py").write_text(
        "class Config:\n    pass\n\n\ndef load() -> Config:\n    return Config()\n"
    )

    diagnostics = _public_api_diagnostics(tmp_path)

    assert diagnostics != (), "a re-exported function's undeclared return type must be reported"
    assert any("Config" in diagnostic.unknown_claim for diagnostic in diagnostics)


def test_public_api_is_silent_for_a_builtin_and_a_declared_collection_element(
    tmp_path: Path,
) -> None:
    """Green regression guard: `archkeel.api.load_violations` takes a bare `Path` and returns
    `tuple[ViolationRow, ...]` today (AD-70's own current, correct surface). The guard must clear
    a stdlib parameter and a declared type sitting inside a generic, not just a bare declared
    name, or it would fire on the facade it exists to protect.
    """
    _prepare(
        tmp_path,
        ["sample.facade:Row", "sample.facade:load"],
        "from dataclasses import dataclass\n"
        "from pathlib import Path\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class Row:\n"
        "    value: str\n\n\n"
        "def load(path: Path) -> tuple[Row, ...]:\n"
        "    return ()\n",
    )

    assert _public_api_diagnostics(tmp_path) == ()


@pytest.mark.parametrize(
    ("name", "source"),
    [
        (
            "JsonObject",
            "from typing import TypeAlias\n\nJsonObject: TypeAlias = dict[str, object]\n",
        ),
        ("MAX_SIZE", "MAX_SIZE = 10\n"),
        ("Scalar", "Scalar = int\n"),
    ],
)
def test_public_api_accepts_non_callable_symbols_without_function_diagnostics(
    tmp_path: Path, name: str, source: str
) -> None:
    _prepare(
        tmp_path,
        [f"sample.facade:{name}"],
        source,
    )

    assert _public_api_diagnostics(tmp_path) == ()
    result = _observe(tmp_path)
    assert result.observation is not None
    assert not [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "api_surface_limit"
    ]


@pytest.mark.parametrize("entry", ["sample.facade:Child", "sample.model:Child"])
@pytest.mark.parametrize("base", ["Base", "Base[Hidden]"])
def test_public_api_reports_inherited_fields_at_their_origin(
    tmp_path: Path, entry: str, base: str
) -> None:
    _prepare(tmp_path, [entry], "from sample.model import Child\n__all__ = ['Child']\n")
    generic = base != "Base"
    (tmp_path / "sample/model.py").write_text(
        "from typing import Generic, TypeVar\n"
        "from pydantic import BaseModel\n"
        "T = TypeVar('T')\n"
        "class Hidden: pass\n"
        f"class Base(BaseModel{', Generic[T]' if generic else ''}):\n"
        f"    inherited: {'list[T]' if generic else 'Hidden'}\n"
        "    _private: Hidden\n"
        "    def implementation(self) -> Hidden: ...\n"
        f"class Child({base}): pass\n"
    )

    diagnostics = _public_api_diagnostics(tmp_path)

    assert [item.code for item in diagnostics] == ["api_surface.missing"]
    assert "sample.model:Hidden" in diagnostics[0].remedy


@pytest.mark.parametrize(
    "override",
    ["inherited: str", "inherited = 'safe'", "def inherited(self) -> str: ..."],
)
def test_public_api_inherited_fields_respect_subclass_overrides(
    tmp_path: Path, override: str
) -> None:
    _prepare(
        tmp_path,
        ["sample.facade:Child"],
        "class Hidden: pass\n"
        "class Base:\n"
        "    inherited: Hidden\n"
        "class Middle(Base): pass\n"
        "class Child(Middle):\n"
        f"    {override}\n",
    )

    assert _public_api_diagnostics(tmp_path) == ()


@pytest.mark.parametrize(
    ("source", "entry"),
    [
        ("class Child(Missing): pass\n", "sample.facade:Child"),
        ("class Base: pass\nclass Base: pass\nclass Child(Base): pass\n", "sample.facade:Child"),
        (
            "class First: pass\nclass Second: pass\nclass Child(First, Second): pass\n",
            "sample.facade:Child",
        ),
        ("class Base(Child): pass\nclass Child(Base): pass\n", "sample.facade:Child"),
        ("class Child: pass\nclass Child: pass\n", "sample.facade:Child"),
        (
            "from typing import Generic, TypeVar\nT = TypeVar('T')\n"
            "class Hidden: pass\nclass Base(Generic[T]):\n    T = str\n    field: T\n"
            "class Child(Base[Hidden]): pass\n",
            "sample.facade:Child",
        ),
        ("class Base:\n    field: Missing\nclass Child(Base): pass\n", "sample.facade:Child"),
        (
            "class Base:\n    first: Missing\n    second: Missing\nclass Child(Base): pass\n",
            "sample.facade:Child",
        ),
        (
            "from sample.left import Child\nfrom sample.right import Child\n__all__ = ['Child']\n",
            "sample.facade:Child",
        ),
    ],
)
def test_public_api_unproven_inheritance_or_entry_keeps_unknown(
    tmp_path: Path, source: str, entry: str
) -> None:
    _prepare(tmp_path, [entry], source)
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics

    limits = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "api_surface_limit" and entry in item.subjects
    ]
    assert limits, "unproven public fields must not certify API closure"
    assert len({item.id for item in limits}) == len(limits)
    assert limits[0].evidence_ids
    assert limits[0].data.get("reason")


def test_public_api_resolves_an_aliased_base_and_multilevel_generic_fields(tmp_path: Path) -> None:
    _prepare(
        tmp_path,
        ["sample.facade:Child", "sample.model:Hidden"],
        "from typing import Generic, TypeVar\n"
        "from sample.model import Base as Parent, Hidden\n"
        "T = TypeVar('T')\n"
        "class Middle(Parent[T], Generic[T]): pass\n"
        "class Child(Middle[Hidden]): pass\n",
    )
    (tmp_path / "sample/model.py").write_text(
        "from typing import Generic, TypeVar\nT = TypeVar('T')\n"
        "class Hidden: pass\nclass Noise: pass\n"
        "class Base(Generic[T]):\n    field: list[T]\n    _private: Noise\n"
        "    def implementation(self) -> Noise: ...\n"
    )

    assert _public_api_diagnostics(tmp_path) == ()
    result = _observe(tmp_path)
    assert result.observation is not None
    assert not [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "api_surface_limit"
    ]


@pytest.mark.parametrize(
    "alias", ["Alias = Child", "Alias: TypeAlias = Child", "Middle = Child\nAlias = Middle"]
)
@pytest.mark.parametrize("declared", [False, True])
def test_public_api_class_alias_keeps_inherited_fields(
    tmp_path: Path, alias: str, declared: bool
) -> None:
    _prepare(
        tmp_path,
        ["sample.facade:Alias", *(["sample.facade:Hidden"] if declared else [])],
        "from typing import TypeAlias\nclass Hidden: pass\n"
        "class Base:\n    field: Hidden\nclass Child(Base): pass\n" + alias + "\n",
    )
    diagnostics = _public_api_diagnostics(tmp_path)
    assert bool(diagnostics) is not declared
    if not declared:
        assert all("Hidden" in diagnostic.unknown_claim for diagnostic in diagnostics)
    result = _observe(tmp_path)
    assert result.observation is not None
    assert not [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "api_surface_limit"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "Alias = Missing\n",
        "Alias: TypeAlias = Other\nOther: TypeAlias = Alias\n",
        "class Child: pass\nclass Child: pass\nAlias = Child\n",
        "class Child: pass\nAlias = Child\nAlias = str\n",
        "class Child: pass\nAlias: TypeAlias = list[Child]\n",
    ],
)
def test_public_api_unproven_class_alias_retains_unknown(tmp_path: Path, source: str) -> None:
    _prepare(tmp_path, ["sample.facade:Alias"], "from typing import TypeAlias\n" + source)
    result = _observe(tmp_path)
    assert result.observation is not None
    limits = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "api_surface_limit"
    ]
    assert len(limits) == 1
    assert limits[0].subjects == ("sample.facade:Alias",)
    assert limits[0].evidence_ids


@pytest.mark.parametrize("entry", ["Child", "Alias"])
@pytest.mark.parametrize("declared", [False, True])
@pytest.mark.parametrize("component_public", [False, True])
def test_public_api_component_facade_does_not_declare_exposed_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    entry: str,
    declared: bool,
    component_public: bool,
) -> None:
    _prepare(
        tmp_path,
        [
            f"sample.facade:{entry}",
            *(["sample.facade:Hidden", "sample.facade:Own"] if declared else []),
        ],
        "class Hidden: pass\nclass Own: pass\nclass Base:\n    inherited: Hidden\n"
        "class Child(Base):\n    own: Own\nAlias = Child\n",
    )
    contract = json.loads((tmp_path / "contract.json").read_text())
    contract["components"] = [
        _component(
            "sample",
            packages=["sample"],
            public=["sample.facade:Child"] if component_public else [],
        )
    ]
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    result = _observe(tmp_path)
    assert result.observation is not None
    api = next(
        item
        for item in result.observation.records("declarations") or ()
        if item.kind == "declared_public_api" and item.subjects == (f"sample.facade:{entry}",)
    )
    assert api.data.get("types") == (
        () if declared else ("sample.facade:Hidden", "sample.facade:Own")
    )
    diagnostics = _public_api_diagnostics(tmp_path)
    assert bool(diagnostics) is not declared
    if not declared:
        assert any("Hidden" in diagnostic.unknown_claim for diagnostic in diagnostics)
        assert any("Own" in diagnostic.unknown_claim for diagnostic in diagnostics)
    assert not [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "api_surface_limit"
    ]

    _commit_public_api_fixture(tmp_path, ("sample.facade:Child",) if component_public else ())
    assert main(["validate", "--root", str(tmp_path), "--json"]) == (0 if declared else 2)
    validation = json.loads(capsys.readouterr().out)
    assert [item["code"] for item in validation["diagnostics"]] == (
        [] if declared else ["api_surface.missing"] * 2
    )


def test_public_api_member_ambiguity_does_not_hide_known_inherited_fields(tmp_path: Path) -> None:
    _prepare(
        tmp_path,
        ["sample.facade:Child"],
        "class Hidden: pass\nclass Own: pass\nclass Own: pass\n"
        "class Base:\n    inherited: Hidden\nclass Child(Base):\n    own: Own\n",
    )
    contract = json.loads((tmp_path / "contract.json").read_text())
    contract["components"] = [
        _component("sample", packages=["sample"], public=["sample.facade:Child"])
    ]
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    assert any(
        "Hidden" in diagnostic.unknown_claim for diagnostic in _public_api_diagnostics(tmp_path)
    )


@pytest.mark.parametrize(
    ("entries", "source", "exit_code", "status"),
    [
        (["sample:ChildPublic"], "class Child(Base): pass\n", 2, "UNKNOWN"),
        (["sample.facade:Child"], "class Child(Base): pass\n", 2, "UNKNOWN"),
        (["sample:Public"], "class Child(Base): pass\n", 2, "UNKNOWN"),
        (["sample:Public", "sample.facade:Nested"], "class Child(Base): pass\n", 0, "PASS"),
        (["sample:ChildPublic", "sample.facade:Nested"], "class Child(Base): pass\n", 0, "PASS"),
        (["sample:ChildPublic"], "class Child(Missing): pass\n", 0, "UNKNOWN"),
        (["sample.facade:Alias"], "class Child(Base): pass\nAlias = Child\n", 2, "UNKNOWN"),
        (
            ["sample.facade:Alias", "sample.facade:Nested"],
            "class Child(Base): pass\nAlias = Child\n",
            0,
            "PASS",
        ),
        (["sample.facade:Alias"], "class Child(Missing): pass\nAlias = Child\n", 0, "UNKNOWN"),
        (["sample:AliasPublic"], "class Child(Base): pass\nAlias = Child\n", 2, "UNKNOWN"),
        (
            ["sample:AliasPublic", "sample.facade:Nested"],
            "class Child(Base): pass\nAlias = Child\n",
            0,
            "PASS",
        ),
    ],
)
def test_public_api_inheritance_cli_and_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    entries: list[str],
    source: str,
    exit_code: int,
    status: str,
) -> None:
    _prepare(
        tmp_path,
        entries,
        "class Nested:\n    value: str\nclass Exported:\n    item: Nested\n"
        "class Base:\n    inherited: Nested\n" + source,
    )
    (tmp_path / "sample/__init__.py").write_text(
        "from .facade import Child as ChildPublic, Exported as Public\n"
        + (
            "from .facade import Alias as AliasPublic\n"
            "__all__ = ['ChildPublic', 'Public', 'AliasPublic']\n"
            if "sample:AliasPublic" in entries
            else "__all__ = ['ChildPublic', 'Public']\n"
        )
    )
    _commit_public_api_fixture(tmp_path)

    assert main(["validate", "--root", str(tmp_path), "--json"]) == exit_code
    validation = json.loads(capsys.readouterr().out)
    assert validation["declared_rules"] == status, validation
    assert [item["code"] for item in validation["diagnostics"]] == (
        ["api_surface.missing"] if exit_code == 2 else []
    )
    output = tmp_path / "report.json"
    assert main(["report", "--root", str(tmp_path), "--output", str(output), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["declared_rules"] == ("UNKNOWN" if "Missing" in source else "PASS"), report
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    api = next(
        item
        for item in observation.records("declarations") or ()
        if item.kind == "declared_public_api" and item.subjects == (entries[0],)
    )
    assert api.data.get("types") == (("sample.facade:Nested",) if exit_code == 2 else ())
    html = output.with_name("report.report.html").read_text()
    if "Missing" in source:
        assert "unresolved_name" in html
        assert "Public API fields cannot be fully resolved" in html

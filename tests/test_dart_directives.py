# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-97: the Dart profile reads the directive header, and what it cannot read is exit 2.

Every edge of a Dart package is written in the header of a library, so the scanner only has to
read that header exactly: comments (nested), annotations, the string forms a URI may take, and
the directive grammar. Anything it cannot fit is an unverifiable input, never a guess and never
a partial edge set, because a missed edge is a boundary nobody checks. Each case builds its own
tiny package and reads the decoded `imports`/`modules` records, the only place the scanner's
answer is visible from outside.

The builder below is shared by the other `test_dart_*` modules the way `test_analyzer`'s
`_component` is shared: one tiny package shape, so a test states only the file it is about.
"""

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import render_result, run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.model import Observation, ObservationResult, Record, RunResult

NAMESPACE = "app"
PROVENANCE = "docs/app.md"
# Libraries every package gets, each with a declaration so no file is blank (AD-28 exempts blank
# files) and every module has a first line a violation can quote.
LIBRARIES: dict[str, str] = {
    "lib/core/api.dart": "class Api {}\n",
    "lib/core/impl.dart": "class Impl {}\n",
    "lib/core/hidden.dart": "class Hidden {}\n",
    "lib/data/store.dart": "class Store {}\n",
}


def component(label: str, **extra: object) -> dict[str, object]:
    return {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": [f"{NAMESPACE}.{label}"],
        "responsibilities": [],
        "forbidden_responsibilities": [],
        "provenance": [PROVENANCE],
        **extra,
    }


def rule(rule_id: str, kind: str, **fields: object) -> dict[str, object]:
    return {
        "id": rule_id,
        "kind": kind,
        "rationale": "Probe.",
        "provenance": [PROVENANCE],
        "decided_by": "architect",
        **fields,
    }


def default_components() -> list[dict[str, object]]:
    return [
        component("core"),
        component("ui", requires=[{"component": "core", "rationale": "Probe."}]),
        component("data"),
    ]


def dart_package(
    root: Path,
    files: Mapping[str, str],
    *,
    components: Sequence[Mapping[str, object]] | None = None,
    rules: Sequence[Mapping[str, object]] = (),
    declarations: Mapping[str, object] | None = None,
    pubspec: str | None = f"name: {NAMESPACE}\n",
    libraries: Mapping[str, str] = LIBRARIES,
) -> Path:
    """Write and commit one Dart package; `files` add to or replace `libraries`."""
    root.mkdir(parents=True, exist_ok=True)
    contract: dict[str, object] = {
        "schema_version": "2.1.0",
        "components": list(components if components is not None else default_components()),
        "rules": list(rules),
    }
    if declarations is not None:
        contract["declarations"] = dict(declarations)
    (root / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
    (root / "docs").mkdir(exist_ok=True)
    (root / PROVENANCE).write_text("# App\n", encoding="utf-8")
    (root / "archkeel.toml").write_text(
        f'[scan]\nroots = ["lib"]\nnamespace = "{NAMESPACE}"\n'
        'contract = "contract.json"\nlanguage = "dart"\n',
        encoding="utf-8",
    )
    if pubspec is not None:
        (root / "pubspec.yaml").write_text(pubspec, encoding="utf-8")
    for relative, text in {**libraries, **files}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "dart@example.invalid"],
        ["git", "config", "user.name", "Dart"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "package"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return root


def dart_config() -> ScanConfig:
    return ScanConfig(("lib",), NAMESPACE, "contract.json", "0" * 64, language="dart")


def observe_dart(root: Path) -> ObservationResult:
    return observe(
        root,
        roots=("lib",),
        namespace=NAMESPACE,
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=root,
        language="dart",
    )


def report_dart(root: Path) -> tuple[RunResult, Observation | None, dict[str, object]]:
    """`report` on the package: its result, decoded observation and result JSON."""
    result, architecture = run_report(root, config=dart_config(), analyzer=observe)
    observation = (
        parse_observation(decode_canonical_model(json.loads(architecture)))
        if architecture is not None
        else None
    )
    return result, observation, json.loads(render_result(result))


def complete(result: ObservationResult) -> Observation:
    assert result.diagnostics == (), result.diagnostics
    assert result.observation is not None
    return result.observation


def edges(observation: Observation, source: str | None = None) -> set[tuple[str, object]]:
    """(target module, symbol) of every import record, optionally from one source module."""
    return {
        (str(item.data.get("target_module")), item.data.get("symbol"))
        for item in observation.records("imports") or ()
        if source is None or item.data.get("source_module") == source
    }


def import_records(observation: Observation, source: str) -> list[Record]:
    return [
        item
        for item in observation.records("imports") or ()
        if item.data.get("source_module") == source
    ]


def modules(observation: Observation) -> set[str]:
    return {str(item.data.get("qualified_name")) for item in observation.records("modules") or ()}


def assert_unverifiable(
    result: ObservationResult | RunResult, *names: str, kind: str = "parse_error"
) -> None:
    """Exit 2 with a `kind` diagnostic whose subject or claim names every one of `names`."""
    assert result.exit_code == 2, result
    matching = [
        item
        for item in result.diagnostics
        if item.kind == kind
        and all(name in f"{item.subject} {item.unknown_claim}" for name in names)
    ]
    assert matching, result.diagnostics


def _ui(tmp_path: Path, text: str, **extra: str) -> ObservationResult:
    return observe_dart(dart_package(tmp_path / "pkg", {"lib/ui/b.dart": text, **extra}))


# ---------------------------------------------------------------------------------------------
# Tokenizer: what the header may contain around its directives


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        pytest.param(
            "/* outer /* inner import 'package:app/core/hidden.dart'; */\n"
            "   still comment import 'package:app/core/impl.dart'; */\n"
            "import 'package:app/core/api.dart';\n",
            {("app.core.api", None)},
            id="nested-block-comment",
        ),
        pytest.param(
            "/// A doc comment: import 'package:app/core/hidden.dart';\n"
            "// import 'package:app/core/impl.dart';\n"
            "library;\n"
            "/// Documents the import below.\n"
            "import 'package:app/core/api.dart'; // trailing import 'x.dart';\n",
            {("app.core.api", None)},
            id="doc-and-line-comments",
        ),
        pytest.param(
            "#!/usr/bin/env dart\nimport 'package:app/core/api.dart';\n",
            {("app.core.api", None)},
            id="script-line",
        ),
        pytest.param(
            "@TestOn('vm')\n"
            "@Deprecated(\"see (other) api ) 'quoted'\")\n"
            "@immutable\n"
            "@meta.sealed\n"
            "@Tags(['a', 'b'])\n"
            "library app_ui;\n"
            "\n"
            "@deprecated\n"
            "import 'package:app/core/api.dart';\n",
            {("app.core.api", None)},
            id="annotations-before-library-and-import",
        ),
        pytest.param(
            "import r'package:app/core/api.dart';\n",
            {("app.core.api", None)},
            id="raw-uri",
        ),
        pytest.param(
            "import '''package:app/core/api.dart''';\n"
            'import """package:app/core/impl.dart""";\n'
            "import r'''package:app/core/hidden.dart''';\n",
            {("app.core.api", None), ("app.core.impl", None), ("app.core.hidden", None)},
            id="triple-quoted-uris",
        ),
        pytest.param(
            "import 'package:app/' \"core/api.dart\";\n"
            "import 'package:app/core/'\n    r'impl'\n    '.dart';\n",
            {("app.core.api", None), ("app.core.impl", None)},
            id="adjacent-string-concatenation",
        ),
    ],
)
def test_header_forms_yield_exactly_their_edges(
    tmp_path: Path, header: str, expected: set[tuple[str, object]]
) -> None:
    observation = complete(_ui(tmp_path, header + "\nclass B {}\n"))
    assert edges(observation, "app.ui.b") == expected


def test_show_hide_as_and_deferred(tmp_path: Path) -> None:
    observation = complete(
        _ui(
            tmp_path,
            "import 'package:app/core/api.dart' as api show Api, ApiError;\n"
            "import 'package:app/core/impl.dart' hide Secret, Other;\n"
            "import 'package:app/core/hidden.dart' deferred as lazy;\n"
            "import 'package:app/data/store.dart' show Store hide Other;\n"
            "\nclass B {}\n",
        )
    )
    assert edges(observation, "app.ui.b") == {
        ("app.core.api", "Api"),
        ("app.core.api", "ApiError"),
        ("app.core.impl", None),
        ("app.core.hidden", None),
        ("app.data.store", "Store"),
    }
    records = import_records(observation, "app.ui.b")
    assert len(records) == 5
    for item in records:
        symbol = item.data.get("symbol")
        assert item.kind == "import"
        assert item.evidence_class == "FACT"
        assert item.data.get("symbols_known") is (symbol is not None)
        if symbol is not None:
            assert item.data.get("binding") == symbol
        assert item.data.get("reexport") is False
        assert item.data.get("under_type_checking") is False
        assert item.data.get("relative_level") == 0


def test_conditional_import_records_every_alternative(tmp_path: Path) -> None:
    observation = complete(
        _ui(
            tmp_path,
            "import 'package:app/core/api.dart'\n"
            "    if (dart.library.io) 'package:app/core/impl.dart'\n"
            "    if (dart.library.js_interop == 'true') 'package:app/core/hidden.dart'\n"
            "    as platform;\n"
            "export 'package:app/data/store.dart'\n"
            "    if (dart.library.html) 'package:app/core/api.dart' show Store;\n"
            "\nclass B {}\n",
        )
    )
    assert edges(observation, "app.ui.b") == {
        ("app.core.api", None),
        ("app.core.impl", None),
        ("app.core.hidden", None),
        ("app.data.store", "Store"),
        ("app.core.api", "Store"),
    }


def test_export_records_are_reexports(tmp_path: Path) -> None:
    observation = complete(
        _ui(
            tmp_path,
            "export 'package:app/core/api.dart' show Api;\n"
            "export 'package:app/core/impl.dart';\n"
            "\nclass B {}\n",
        )
    )
    records = import_records(observation, "app.ui.b")
    assert sorted(
        (str(item.data.get("target_module")), item.data.get("symbol"), item.data.get("reexport"))
        for item in records
    ) == [("app.core.api", "Api", True), ("app.core.impl", None, True)]


@pytest.mark.parametrize(
    "part_of",
    ["part of 'b.dart';", "part of 'package:app/ui/b.dart';", "part of app_ui;"],
)
def test_part_is_read_but_is_not_a_module(tmp_path: Path, part_of: str) -> None:
    result = _ui(
        tmp_path,
        "library app_ui;\nimport 'package:app/core/api.dart';\npart 'b_part.dart';\n\nclass B {}\n",
        **{"lib/ui/b_part.dart": f"{part_of}\n\nclass BPart {{}}\n"},
    )
    observation = complete(result)
    assert "app.ui.b" in modules(observation)
    assert "app.ui.b_part" not in modules(observation)
    assert not any(str(module).startswith("app.ui.b_part") for module in modules(observation))
    # The part is discovered, read and parsed: coverage counts all six files.
    assert observation.coverage.files_discovered == len(LIBRARIES) + 2
    assert observation.coverage.files_parsed == len(LIBRARIES) + 2
    assert edges(observation) == {("app.core.api", None)}


def test_orphan_part_is_unverifiable(tmp_path: Path) -> None:
    result = _ui(
        tmp_path,
        "import 'package:app/core/api.dart';\n\nclass B {}\n",
        **{"lib/ui/orphan.dart": "part of 'b.dart';\n\nclass Orphan {}\n"},
    )
    assert_unverifiable(result, "lib/ui/orphan.dart")


def test_first_declaration_ends_the_header(tmp_path: Path) -> None:
    observation = complete(
        _ui(
            tmp_path,
            "import 'package:app/core/api.dart';\n"
            "\n"
            "class B {\n"
            "  String render() {\n"
            "    const text = '''\n"
            "import 'package:app/core/impl.dart';\n"
            "export 'package:app/core/hidden.dart';\n"
            "''';\n"
            "    return \"import 'package:app/data/store.dart';\" + text;\n"
            "  }\n"
            "}\n",
        )
    )
    assert edges(observation, "app.ui.b") == {("app.core.api", None)}


@pytest.mark.parametrize(
    "uri",
    [
        "'package:app/core/$name.dart'",
        "'package:app/${folder}/api.dart'",
        '"package:app/core/${name}.dart"',
        "'package:app/' '$core/api.dart'",
    ],
)
def test_interpolated_uri_is_unverifiable(tmp_path: Path, uri: str) -> None:
    result = _ui(tmp_path, f"import {uri};\n\nclass B {{}}\n")
    assert_unverifiable(result, "lib/ui/b.dart")


@pytest.mark.parametrize(
    "header",
    [
        pytest.param("import 'package:app/core/api.dart'\nclass B {}\n", id="missing-semicolon"),
        pytest.param("import package:app/core/api.dart;\nclass B {}\n", id="unquoted-uri"),
        pytest.param("import;\nclass B {}\n", id="no-uri"),
        pytest.param("import 'package:app/core/api.dart' show ;\nclass B {}\n", id="empty-show"),
        pytest.param(
            "import 'package:app/core/api.dart' as ;\nclass B {}\n", id="as-without-prefix"
        ),
        pytest.param(
            "import 'package:app/core/api.dart'\n"
            "    if (dart.library.io 'package:app/core/impl.dart';\nclass B {}\n",
            id="unbalanced-condition",
        ),
        pytest.param("import 'package:app/core/api.dart;\nclass B {}\n", id="unterminated"),
        pytest.param(
            "/* never closed /* nested */\nimport 'package:app/core/api.dart';\nclass B {}\n",
            id="unterminated-block-comment",
        ),
        pytest.param(
            "@Annotation('x'\nimport 'package:app/core/api.dart';\nclass B {}\n",
            id="unbalanced-annotation",
        ),
        pytest.param("part;\nclass B {}\n", id="part-without-uri"),
    ],
)
def test_malformed_header_is_unverifiable(tmp_path: Path, header: str) -> None:
    assert_unverifiable(_ui(tmp_path, header), "lib/ui/b.dart")


# ---------------------------------------------------------------------------------------------
# Mapping: URI -> module id


def test_own_package_and_relative_uris_resolve_to_scanned_modules(tmp_path: Path) -> None:
    observation = complete(
        _ui(
            tmp_path,
            "import 'package:app/core/api.dart';\n"
            "import '../core/impl.dart';\n"
            "import 'c.dart';\n"
            "import './widgets/d.dart';\n"
            "\nclass B {}\n",
            **{"lib/ui/c.dart": "class C {}\n", "lib/ui/widgets/d.dart": "class D {}\n"},
        )
    )
    assert edges(observation, "app.ui.b") == {
        ("app.core.api", None),
        ("app.core.impl", None),
        ("app.ui.c", None),
        ("app.ui.widgets.d", None),
    }
    assert {
        "app.core.api",
        "app.core.impl",
        "app.core.hidden",
        "app.data.store",
        "app.ui.b",
        "app.ui.c",
        "app.ui.widgets.d",
    } == modules(observation)


def test_module_record_carries_package_and_file(tmp_path: Path) -> None:
    observation = complete(_ui(tmp_path, "class B {}\n"))
    (record,) = [
        item
        for item in observation.records("modules") or ()
        if item.data.get("qualified_name") == "app.ui.b"
    ]
    assert record.data.get("package") == "app.ui"
    assert record.data.get("file") == "lib/ui/b.dart"


@pytest.mark.parametrize(
    "uri", ["'../../tool/x.dart'", "'../../../outside.dart'", "'../../lib_other/x.dart'"]
)
def test_relative_uri_escaping_the_scan_root_is_unverifiable(tmp_path: Path, uri: str) -> None:
    result = _ui(
        tmp_path,
        f"import {uri};\n\nclass B {{}}\n",
        **{"tool/x.dart": "class X {}\n", "lib_other/x.dart": "class X {}\n"},
    )
    assert_unverifiable(result, "lib/ui/b.dart")


@pytest.mark.parametrize(
    "uri",
    [
        "'package:app/core/missing.dart'",
        "'missing.dart'",
        "'package:app/core/api.g.dart'",
    ],
)
def test_unresolved_own_import_is_unverifiable(tmp_path: Path, uri: str) -> None:
    assert_unverifiable(_ui(tmp_path, f"import {uri};\n\nclass B {{}}\n"), "lib/ui/b.dart")


def test_dart_and_other_package_uris_are_external(tmp_path: Path) -> None:
    observation = complete(
        _ui(
            tmp_path,
            "import 'dart:io';\n"
            "import 'dart:async' show Future;\n"
            "import 'package:http/http.dart' as http;\n"
            "import 'package:flutter_bloc/src/bloc-base.dart';\n"
            "\nclass B {}\n",
        )
    )
    assert edges(observation, "app.ui.b") == {
        ("dart.io", None),
        ("dart.async", "Future"),
        ("http.http", None),
        ("flutter_bloc.src.bloc_base", None),
    }
    assert not {"dart.io", "http.http"} & modules(observation)


def test_path_segments_become_identifiers(tmp_path: Path) -> None:
    observation = complete(
        _ui(
            tmp_path,
            "import 'package:app/core/app.config.dart';\n"
            "import '../core/my-widget.dart';\n"
            "\nclass B {}\n",
            **{
                "lib/core/app.config.dart": "class AppConfig {}\n",
                "lib/core/my-widget.dart": "class MyWidget {}\n",
            },
        )
    )
    assert {"app.core.app_config", "app.core.my_widget"} <= modules(observation)
    assert edges(observation, "app.ui.b") == {
        ("app.core.app_config", None),
        ("app.core.my_widget", None),
    }


def test_generated_libraries_are_scanned(tmp_path: Path) -> None:
    observation = complete(
        _ui(
            tmp_path,
            "class B {}\n",
            **{"lib/core/injection.config.dart": "import 'package:app/data/store.dart';\n"},
        )
    )
    assert edges(observation, "app.core.injection_config") == {("app.data.store", None)}


def test_two_files_mapping_to_one_module_id_are_unverifiable(tmp_path: Path) -> None:
    result = _ui(
        tmp_path,
        "class B {}\n",
        **{"lib/core/a.b.dart": "class A {}\n", "lib/core/a_b.dart": "class A {}\n"},
    )
    assert_unverifiable(result, "lib/core/a.b.dart", "lib/core/a_b.dart")


def test_segment_that_is_no_identifier_is_unverifiable(tmp_path: Path) -> None:
    result = _ui(tmp_path, "class B {}\n", **{"lib/core/2fa.dart": "class TwoFactor {}\n"})
    assert_unverifiable(result, "lib/core/2fa.dart")


def _cli_report(root: Path) -> tuple[int, dict[str, object]]:
    run = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", "report", "--root", str(root), "--json"],
        capture_output=True,
        text=True,
    )
    return run.returncode, json.loads(run.stdout)


def test_pubspec_name_differing_from_namespace_is_unverifiable(tmp_path: Path) -> None:
    root = dart_package(tmp_path / "pkg", {"lib/ui/b.dart": "class B {}\n"}, pubspec="name: shop\n")
    code, payload = _cli_report(root)
    assert code == 2
    diagnostics = payload["diagnostics"]
    assert isinstance(diagnostics, list)
    assert any(
        item["kind"] == "parse_error"
        and "shop" in f"{item['subject']} {item['unknown_claim']}"
        and "app" in f"{item['subject']} {item['unknown_claim']}"
        for item in diagnostics
    ), diagnostics


@pytest.mark.parametrize(
    "pubspec",
    [
        "name: app\n",
        "# The package.\nname: 'app' # own name\nversion: 1.0.0\n",
        'description: x\nname: "app"\ndependencies:\n  name: other\n',
        None,
    ],
)
def test_matching_or_absent_pubspec_passes(tmp_path: Path, pubspec: str | None) -> None:
    root = dart_package(tmp_path / "pkg", {"lib/ui/b.dart": "class B {}\n"}, pubspec=pubspec)
    code, payload = _cli_report(root)
    assert code == 0, payload
    assert payload["observation_complete"] == "PASS"


# ---------------------------------------------------------------------------------------------
# Determinism


def test_two_scans_of_the_same_bytes_are_identical(tmp_path: Path) -> None:
    files = {
        "lib/ui/b.dart": "/* a /* b */ */\n@immutable\nlibrary app_ui;\n"
        "import 'package:app/core/api.dart' show Api;\n"
        "import '../core/impl.dart' if (dart.library.io) '../core/hidden.dart';\n"
        "import 'dart:io';\n"
        "export 'package:app/data/store.dart';\n"
        "part 'b_part.dart';\n\nclass B {}\n",
        "lib/ui/b_part.dart": "part of 'b.dart';\n\nclass BPart {}\n",
        "lib/ui/z.dart": "import 'b.dart';\n\nclass Z {}\n",
    }
    first = dart_package(tmp_path / "first", files)
    second = tmp_path / "elsewhere" / "second"
    second.parent.mkdir()
    subprocess.run(["git", "clone", "-q", str(first), str(second)], check=True, capture_output=True)
    _, one = run_report(first, config=dart_config(), analyzer=observe)
    _, again = run_report(first, config=dart_config(), analyzer=observe)
    _, other = run_report(second, config=dart_config(), analyzer=observe)
    assert one is not None
    assert one == again == other
    model = json.loads(one)
    assert model["analyzer"]["name"] == "archkeel-dart-directives"

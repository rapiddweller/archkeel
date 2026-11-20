# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The CLI names Python test sources left out of an explicit scope."""

from pathlib import Path

from test_cli_core_only_scan import command
from test_cli_native_python_imports import BASE, project, verdict


def test_python_excluded_test_paths_are_visible_in_json_and_text(
    release_core: Path, tmp_path: Path
) -> None:
    root = project(tmp_path, {**BASE, "src/app/test_client.py": "", "src/app/latest.py": ""})
    config = root / "archkeel.toml"
    included = verdict(release_core, root)
    assert not included["frame"].get("excluded_sources")
    config.write_text(config.read_text() + "exclude_test_sources = true\n")
    result = verdict(release_core, root)
    assert result["frame"]["excluded_sources"] == ["src/app/test_client.py"]
    text = command(release_core, root, "--text").stdout
    assert "Excluded test sources:" in text
    assert "src/app/test_client.py" in text

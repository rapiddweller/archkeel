# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The dual run must name unsupported cases rather than compare a supported subset silently."""

import pytest

from tools.dual_run_corpus import Case


@pytest.mark.parametrize("language", ["python", "dart", "typescript", "rust"])
def test_case_language_reads_the_effective_configuration(tmp_path, language):
    from tools.dual_run_corpus import case_language

    (tmp_path / "archkeel.toml").write_text('[scan]\nlanguage = "python"\n')
    case = Case(
        "example", str(tmp_path), files={"archkeel.toml": f'[scan]\nlanguage = "{language}"\n'}
    )
    assert case_language(case) == language


def test_supported_split_names_and_counts_both_unsupported_languages(tmp_path, capsys):
    from tools.dual_run import supported_cases

    cases = [
        Case(language, "", files={"archkeel.toml": f'[scan]\nlanguage = "{language}"\n'})
        for language in ("python", "dart", "typescript", "rust")
    ]
    kept, skipped = supported_cases(cases)
    assert [case.id for case in kept] == ["typescript", "rust"]
    assert skipped == 2
    text = capsys.readouterr().out
    assert "SKIP python: python" in text
    assert "SKIP dart: dart" in text
    assert "use archkeel 4.0.1" in text


def test_committed_case_uses_the_config_path_of_the_archive(monkeypatch):
    from tools.dual_run_corpus import case_language

    def read(command, **kwargs):
        assert command == ["git", "show", f"{'a' * 40}:native/archkeel.toml"]
        return '[scan]\nlanguage = "rust"\n'

    monkeypatch.setattr("tools.dual_run_corpus.subprocess.check_output", read)
    assert (
        case_language(Case("native", "native", "native/archkeel.toml", commit="a" * 40)) == "rust"
    )

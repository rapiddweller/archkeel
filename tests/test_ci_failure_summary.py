# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1060: a failed test job names its first failing test and how to repeat it."""

from pathlib import Path

from tools.ci_failure_summary import first_failure, main, render

SUITE = (
    "<testsuites><testsuite>"
    '<testcase classname="tests.test_a" name="test_ok"/>'
    '<testcase classname="tests.test_b" name="test_bad[200000]">'
    '<failure message="TimeoutExpired: 60 s&#10;more">trace</failure></testcase>'
    '<testcase classname="tests.test_c" name="test_later"><error message="x"/></testcase>'
    "</testsuite></testsuites>"
)


def test_the_first_failed_or_errored_case_wins(tmp_path: Path) -> None:
    junit = tmp_path / "results.xml"
    junit.write_text(SUITE)
    assert first_failure(junit) == ("tests.test_b::test_bad[200000]", "TimeoutExpired: 60 s")
    junit.write_text(SUITE.replace("<failure", "<skipped").replace("</failure>", "</skipped>"))
    assert first_failure(junit) == ("tests.test_c::test_later", "x")


def test_a_green_file_a_missing_file_and_a_broken_file_each_say_so(tmp_path: Path) -> None:
    junit = tmp_path / "results.xml"
    assert "no JUnit file" in render("job", junit, "make x", "art")
    junit.write_text("<bad")
    assert "no JUnit file" in render("job", junit, "make x", "art")
    junit.write_text('<testsuites><testcase classname="a" name="b"/></testsuites>')
    assert "no failed test" in render("job", junit, "make x", "art")


def test_the_summary_carries_the_command_and_the_artifact(tmp_path: Path, capsys) -> None:
    junit = tmp_path / "results.xml"
    junit.write_text(SUITE)
    args = [
        "--job",
        "CLI",
        "--junit",
        str(junit),
        "--reproduce",
        "make full-test",
        "--artifact",
        "a",
    ]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "first failing test `tests.test_b::test_bad[200000]`" in out
    assert "`make full-test`" in out and "artifact `a`" in out

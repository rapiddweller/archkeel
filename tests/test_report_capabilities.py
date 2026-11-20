# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Capability statistics use only the rule rows of the actual run."""

from tools.report_capabilities import page
from tools.report_gallery import summarize


def test_capabilities_show_rule_results_and_missing_runs() -> None:
    envelope = {
        "exit_code": 2,
        "status": "UNKNOWN",
        "gaps": [],
        "frame": {
            "rules": {
                "R<1": ["forbidden_dependency", "PASS"],
                "R2": ["forbidden_dependency", "UNKNOWN"],
                "R4": ["forbidden_dependency", "FAIL"],
            },
            "violations": {"R4": 1},
            "details": {"R4": [{"cause": "undeclared dependency", "evidence": ["site"]}]},
            "locations": {"site": {"path": "src/shop.py", "line": 8}},
            "unknown_kinds": {"R2": "no_receipt"},
            "premises": {"R<1": [{"kind": "standard_library_unchanged", "subject": "a.fn:x"}]},
            "explained": {"R2": "no module was selected"},
            "self_test": {
                "contract": {
                    "rules": {
                        "R<1": "forbidden_dependency",
                        "R2": "forbidden_dependency",
                        "R3": "unused_public",
                    }
                }
            },
            "unsupported": {"rules": {"R3": "not supported"}},
            "explain": {
                "rules": {"R<1": {"source": ["a"], "target": ["b"], "direction": "forward"}}
            },
        },
    }
    rows = [
        {
            "run": {"name": "self"},
            "summary": summarize(envelope),
            "frame": envelope["frame"],
            "links": [("HTML", "self/core.html")],
        },
        {"run": {"name": "demo"}, "error": "missing <source>", "links": []},
        {
            "run": {"name": "plant", "plant": {}, "counterexample": True},
            "summary": summarize(envelope),
            "frame": envelope["frame"],
            "links": [],
        },
    ]
    result = page(rows[:1], rows[1:])
    assert "forbidden_dependency" in result
    assert "R&lt;1" in result and "a → b" in result
    assert "no_receipt: no module was selected" in result and "UNKNOWN" in result
    assert "standard_library_unchanged (a.fn:x)" in result
    assert "missing &lt;source&gt;" in result
    assert 'href="self/core.html"' in result
    assert "6 rule results" in result
    assert "1 violation" in result and "undeclared dependency (src/shop.py:8)" in result
    assert "ArchKeel self" in result and "Regular demos" in result
    assert "Intentional counterexamples" in result
    assert (
        "<td>ArchKeel self</td><td>1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td>"
        in result
    )
    assert (
        "<td>Regular demos</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td><td>1</td>"
        in result
    )
    assert (
        "<td>Intentional counterexamples</td><td>1</td><td>1</td><td>1</td>"
        "<td>0</td><td>1</td><td>0</td>" in result
    )
    assert "R3" in result and "NO ROW" in result and "not supported" in result

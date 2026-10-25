# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Guarded path facts keep their values and scan each class declaration once."""

from test_analyzer import _parsed_module

from archkeel.analyzer.python import calls
from archkeel.analyzer.python.resolve import build_symbol_index

GUARDED_MODULE = """class Service:
    flag: bool
    def __init__(self):
        self.other: bool = False
    def run(self):
        return 1
    def guarded(self):
        if self.flag:
            self.run()
    def unrelated(self):
        self.run()
def helper():
    return 1
def start(enabled: bool):
    if enabled:
        helper()
"""


def _projection(collector):
    guarded = [
        ((function.name, name), _locations(by_location))
        for (function, name), by_location in collector.guarded_paths.items()
    ]
    members = [
        (
            (function.name, name),
            (class_node.name, declaration.lineno, _locations(by_location)),
        )
        for (function, name), (class_node, declaration, by_location) in (
            collector.member_paths.items()
        )
    ]
    return guarded, members


def _locations(by_location):
    return {
        location: tuple(
            (path.call_name, path.condition_value, path.unknown_reason) for path in paths
        )
        for location, paths in by_location.items()
    }


def test_guarded_path_facts_keep_values_and_order():
    collector = calls.CallCollector(
        _parsed_module(GUARDED_MODULE, module="sample.core"), build_symbol_index([]), {}
    )

    guarded, members = _projection(collector)

    assert guarded == [(("start", "enabled"), {(16, 8): (("helper", True, None),)})]
    assert members == [
        (("__init__", "flag"), ("Service", 2, {})),
        (("__init__", "other"), ("Service", 4, {})),
        (("run", "flag"), ("Service", 2, {})),
        (("run", "other"), ("Service", 4, {})),
        (("guarded", "flag"), ("Service", 2, {(9, 12): (("self.run", True, None),)})),
        (("guarded", "other"), ("Service", 4, {(9, 12): (("self.run", None, None),)})),
        (("unrelated", "flag"), ("Service", 2, {(11, 8): (("self.run", None, None),)})),
        (("unrelated", "other"), ("Service", 4, {(11, 8): (("self.run", None, None),)})),
    ]


def test_class_bool_declarations_are_scanned_once_for_thirty_methods(monkeypatch):
    methods = "".join(
        f"    def method_{number}(self):\n        self.run()\n" for number in range(30)
    )
    module = _parsed_module(
        "class Service:\n    flag: bool\n" + methods + "    def run(self):\n        return 1\n",
        module="sample.core",
    )
    scans = []
    original = calls.CallCollector._bool_declarations

    def count_scans(collector, parent, receiver_name):
        scans.append((parent.name, receiver_name))
        return original(collector, parent, receiver_name)

    monkeypatch.setattr(calls.CallCollector, "_bool_declarations", count_scans)

    calls.CallCollector(module, build_symbol_index([]), {})

    assert scans == [("Service", "self")]


def test_sequential_ifs_keep_every_path_record_in_order():
    body = "".join(
        f"        if value_{number}:\n            total_{number} = 1\n" for number in range(6)
    )
    module = _parsed_module(
        "class Service:\n    flag: bool\n    def busy(self):\n"
        + body
        + "        self.run()\n    def run(self):\n        return 1\n",
        module="sample.core",
    )

    collector = calls.CallCollector(module, build_symbol_index([]), {})

    [paths] = [
        by_location
        for (function, name), (_, _, by_location) in collector.member_paths.items()
        if function.name == "busy" and name == "flag"
    ]
    [records] = paths.values()
    assert len(records) == 2**6
    assert {(record.call_name, record.condition_value) for record in records} == {
        ("self.run", None)
    }

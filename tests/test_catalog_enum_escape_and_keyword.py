# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Catalog enum members: escape anywhere in the snapshot, and keyword argument evidence (#620)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_catalog_policy_native import _argument, _read_option_use, _run, _use

from archkeel.check.report import run_saved_report
from archkeel.ir.codec import encode_canonical_model, observation_payload

HEAD = "from .catalog import OptionKey, read_option\n"
CONSUME = "def consume():\n    read_option(OptionKey.PAGE_SIZE)\n"
MUTATE = "def mutate(member):\n    member._value_ = 'changed'\n"
TARGET = "sample.catalog.read_option"


def _verdicts(tmp_path: Path, **run_arguments):
    """Return the verdict of the in-memory run; the saved replay must agree in both encodings."""
    result, rows = _run(tmp_path, **run_arguments)
    verdict = (rows[0].status, rows[0].evaluation_proven)
    payload = observation_payload(result.observation)
    for columnar in (False, True):
        saved = tmp_path / f"saved-{columnar}.json"
        saved.write_bytes(
            json.dumps(encode_canonical_model(payload) if columnar else payload).encode()
        )
        [replayed] = run_saved_report(saved).rule_assessments
        assert (replayed.status, replayed.evaluation_proven) == verdict
    return verdict


def _argument_rule(target: str = TARGET):
    return {**_argument(), "target": target}


# --- (a) escape analysis uses every call and reference of the snapshot ---------------------

# Each form puts one catalog member in a place the collector exempts from owner exposure
# (a call argument). The check must see it outside the selected source too.
CALL_ESCAPES = {
    "resolved-mutator": MUTATE + "def go():\n    mutate(OptionKey.PAGE_SIZE)\n",
    "keyword-argument": MUTATE + "def go():\n    mutate(member=OptionKey.PAGE_SIZE)\n",
    "starred-argument": MUTATE + "def go():\n    mutate(*[OptionKey.PAGE_SIZE])\n",
    "nested-argument": MUTATE + "def go():\n    mutate([OptionKey.PAGE_SIZE])\n",
    "multiline-call": MUTATE + "def go():\n    mutate(\n        OptionKey.PAGE_SIZE\n    )\n",
    "unresolved-callee": "def go():\n    opaque(OptionKey.PAGE_SIZE)\n",
    "method-callee": (
        "class C:\n    def m(self, k):\n        k._value_ = 1\n"
        "def go():\n    C().m(OptionKey.PAGE_SIZE)\n"
    ),
    "setattr": "def go():\n    setattr(OptionKey.PAGE_SIZE, '_value_', 'x')\n",
    "benign-callee": "def go():\n    print(OptionKey.PAGE_SIZE)\n",
    "list-append": "ITEMS = []\ndef go():\n    ITEMS.append(OptionKey.PAGE_SIZE)\n",
}


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("where", ["outside-source", "inside-source"])
@pytest.mark.parametrize("form", CALL_ESCAPES)
def test_member_reaching_any_call_but_the_selected_target_keeps_argument_unknown(
    tmp_path, form, where, mounted
):
    body = CALL_ESCAPES[form]
    if where == "inside-source":
        caller, extra = HEAD + CONSUME + body, {}
    else:
        caller, extra = HEAD + CONSUME, {"sample/other.py": HEAD + body}
    verdict = _verdicts(
        tmp_path, caller=caller, rules=[_argument_rule()], extra_files=extra, mounted=mounted
    )
    assert verdict == ("UNKNOWN", False)


# These forms already fail closed in the collector. They stay UNKNOWN; this guards the class.
COLLECTOR_ESCAPES = {
    "container-list": "ITEMS = [OptionKey.PAGE_SIZE]\n",
    "container-dict": "ITEMS = {OptionKey.PAGE_SIZE: 1}\n",
    "attribute-assignment": "OptionKey.PAGE_SIZE._value_ = 'x'\n",
    "module-alias": "K = OptionKey.PAGE_SIZE\nK._value_ = 'x'\n",
    "owner-alias": "Alias = OptionKey\nAlias.PAGE_SIZE._value_ = 'x'\n",
    "members-mapping": "OptionKey.__members__['PAGE_SIZE']._value_ = 'x'\n",
    "vars-mapping": "vars(OptionKey)['PAGE_SIZE']._value_ = 'x'\n",
    "member-dunder-setattr": "OptionKey.PAGE_SIZE.__setattr__('_value_', 'x')\n",
    # Other ways to get a member than `OptionKey.PAGE_SIZE` (#731).
    "owner-subscript": "OptionKey['PAGE_SIZE']._value_ = 'x'\n",
    "member-map": "OptionKey._member_map_['PAGE_SIZE']._value_ = 'x'\n",
    "value-map": "OptionKey._value2member_map_['page_size']._value_ = 'x'\n",
    "owner-dict": "OptionKey.__dict__['PAGE_SIZE']._value_ = 'x'\n",
    "owner-iteration": "for m in OptionKey:\n    m._value_ = 'x'\n",
    "owner-list": "list(OptionKey)[0]._value_ = 'x'\n",
    "owner-sorted": "sorted(OptionKey)[0]._value_ = 'x'\n",
    "owner-getattr": "getattr(OptionKey, 'PAGE_SIZE')._value_ = 'x'\n",
    "owner-dunder-call": "OptionKey.__call__('page_size')._value_ = 'x'\n",
    "member-class-call": "OptionKey.PAGE_SIZE.__class__('page_size')._value_ = 'x'\n",
    "owner-partial": "import functools\n"
    "functools.partial(OptionKey, 'page_size')()._value_ = 'x'\n",
    "owner-local-alias": "def go():\n    A = OptionKey\n    A('page_size')._value_ = 'x'\n",
    "missing-hook-assignment": "OptionKey._missing_ = classmethod(lambda cls, v: None)\n",
}


@pytest.mark.parametrize("where", ["outside-source", "inside-source"])
@pytest.mark.parametrize("form", COLLECTOR_ESCAPES)
def test_member_stored_or_mutated_without_a_call_keeps_argument_unknown(tmp_path, form, where):
    body = COLLECTOR_ESCAPES[form]
    if where == "inside-source":
        caller, extra = HEAD + CONSUME + body, {}
    else:
        caller, extra = HEAD + CONSUME, {"sample/other.py": HEAD + body}
    verdict = _verdicts(tmp_path, caller=caller, rules=[_argument_rule()], extra_files=extra)
    assert verdict == ("UNKNOWN", False)


@pytest.mark.parametrize("mounted", [False, True])
def test_member_passed_to_the_selected_target_from_another_module_still_passes(tmp_path, mounted):
    verdict = _verdicts(
        tmp_path,
        caller=HEAD + CONSUME,
        rules=[_argument_rule()],
        extra_files={"sample/other.py": HEAD + "def go():\n    read_option(OptionKey.PAGE_SIZE)\n"},
        mounted=mounted,
    )
    assert verdict == ("PASS", True)


def test_member_named_only_in_an_annotation_elsewhere_still_passes(tmp_path):
    verdict = _verdicts(
        tmp_path,
        caller=HEAD + CONSUME,
        rules=[_argument_rule()],
        extra_files={
            "sample/other.py": "from typing import Literal\n"
            "from .catalog import OptionKey\n"
            "def typed(value: Literal[OptionKey.PAGE_SIZE]) -> None: ...\n"
        },
    )
    assert verdict == ("PASS", True)


def test_member_passed_to_a_selected_target_that_calls_something_is_unknown(tmp_path):
    verdict = _verdicts(
        tmp_path,
        caller="from .ops import read_option\n"
        "from .catalog import OptionKey\n"
        "def consume():\n    read_option(OptionKey.PAGE_SIZE)\n",
        rules=[_argument_rule("sample.ops.read_option")],
        extra_files={"sample/ops.py": "def read_option(key):\n    print(key)\n"},
    )
    assert verdict == ("UNKNOWN", False)


def test_member_passed_to_a_mutating_selected_target_from_another_module_is_unknown(tmp_path):
    verdict = _verdicts(
        tmp_path,
        caller="from .ops import read_option\n"
        "from .catalog import OptionKey\n"
        "def consume():\n    read_option(OptionKey.PAGE_SIZE)\n",
        rules=[_argument_rule("sample.ops.read_option")],
        extra_files={
            "sample/ops.py": "def read_option(key):\n    key._value_ = 'changed'\n",
            "sample/other.py": "from .ops import read_option\nfrom .catalog import OptionKey\n"
            "def go():\n    read_option(OptionKey.PAGE_SIZE)\n",
        },
    )
    assert verdict == ("UNKNOWN", False)


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("where", ["outside-source", "inside-source"])
def test_catalog_use_by_member_reference_is_unaffected_by_escape(tmp_path, where, mounted):
    # A read stays a read; AD-251 counts syntactic reads and the use inventory ignores exposure.
    body = MUTATE + "def go():\n    mutate(OptionKey.PAGE_SIZE)\n"
    if where == "inside-source":
        caller, extra = HEAD + CONSUME + body, {}
    else:
        caller, extra = HEAD + CONSUME, {"sample/other.py": HEAD + body}
    verdict = _verdicts(
        tmp_path,
        caller=caller,
        rules=[{**_read_option_use(), "target": TARGET}],
        extra_files=extra,
        mounted=mounted,
    )
    assert verdict == ("PASS", True)


# --- (a) continued: any owner read that is not a member read is an escape (#731) -----------

# `OptionKey('page_size')` returns the PAGE_SIZE member itself, so a call of the owner gives
# the member away like `OptionKey['PAGE_SIZE']`. The other forms hide a member read inside an
# attribute chain or a write target, where no reference record named it before.
# `f` returns its argument, so `f(member)` gives the member to its caller.
PASS_THROUGH = "def f(value):\n    return value\n"
KEEP = "from typing import Annotated\ndef keep(value):\n    return value\n"
OWNER_ESCAPES = {
    # One row for each way to read the bare owner: in a write target, as an argument, and in
    # a comprehension scope.
    "call-in-function": "def go():\n    OptionKey('page_size')._value_ = 'x'\n",
    "call-result-argument": "def go():\n    print(OptionKey('page_size'))\n",
    "call-in-comprehension": "def go():\n    return [OptionKey(v) for v in ('page_size',)]\n",
    "call-through-module": "from . import catalog\n"
    "def go():\n    catalog.OptionKey('page_size')._value_ = 'x'\n",
    "call-through-import-alias": "import sample.catalog as c\n"
    "def go():\n    c.OptionKey('page_size')._value_ = 'x'\n",
    "type-of-member-call": "def go():\n    type(OptionKey.PAGE_SIZE)('page_size')._value_ = 'x'\n",
    "member-in-write-target": PASS_THROUGH + "def go():\n    f(OptionKey.PAGE_SIZE).x = 1\n",
    # The excerpt of a continuation line does not parse, so the read has an unknown context.
    "call-on-continuation-line": "def go():\n    x = [1,\n         OptionKey('page_size')]\n",
    "member-attribute-argument": PASS_THROUGH + "def go():\n    f(OptionKey.PAGE_SIZE.__dict__)\n",
    "member-method-argument": PASS_THROUGH + "def go():\n    f(OptionKey.PAGE_SIZE.upper())\n",
    "member-value-argument": "def go():\n    print(OptionKey.PAGE_SIZE.value)\n",
    # A wider value that starts with the member is not the member, also for the operation.
    "member-attribute-to-operation": "def go():\n    read_option(OptionKey.PAGE_SIZE.__dict__)\n",
    "owner-mapping-method": "def go():\n"
    "    OptionKey._value2member_map_.get('page_size')._value_ = 'x'\n",
    "owner-hook-call": "def go():\n    OptionKey._missing_('page_size')\n",
    # Without `from __future__ import annotations`, a call in an annotation runs.
    "member-in-annotation-call": KEEP + "X: Annotated[str, keep(OptionKey.PAGE_SIZE)] = 'a'\n",
    "owner-call-in-parameter-annotation": KEEP
    + "def f(v: Annotated[str, keep(OptionKey('page_size'))]) -> None: ...\n",
    "owner-call-as-annotation": "def f(v: OptionKey('page_size').__setattr__('_value_', 'x')) "
    "-> None: ...\n",
}


# The policy reads the whole snapshot, so one form covers the source and mount variants.
@pytest.mark.parametrize(
    ("form", "where", "mounted"),
    [(form, "outside-source", False) for form in OWNER_ESCAPES]
    + [("call-in-function", "inside-source", False), ("call-in-function", "outside-source", True)],
)
def test_owner_read_that_is_not_a_member_read_keeps_argument_unknown(
    tmp_path, form, where, mounted
):
    body = OWNER_ESCAPES[form]
    if where == "inside-source":
        caller, extra = HEAD + CONSUME + body, {}
    else:
        caller, extra = HEAD + CONSUME, {"sample/other.py": HEAD + body}
    verdict = _verdicts(
        tmp_path, caller=caller, rules=[_argument_rule()], extra_files=extra, mounted=mounted
    )
    assert verdict == ("UNKNOWN", False)


# A module that imports the owner gives it away again as its own attribute.
API = {"sample/api.py": "from .catalog import OptionKey\n"}
PACKAGE = {"sample/__init__.py": "from .catalog import OptionKey\n"}
STAR_API = {"sample/api.py": "from .catalog import *\n"}
MODULE_API = {"sample/api.py": "from . import catalog\n"}
WRITE = "('page_size')._value_ = 'x'\n"
REEXPORT_ESCAPES = {
    "from-reexport": (API, "from .api import OptionKey\nOptionKey" + WRITE),
    "from-reexport-alias": (API, "from .api import OptionKey as K\nK" + WRITE),
    "reexport-attribute": (API, "from . import api\napi.OptionKey" + WRITE),
    "from-package": (PACKAGE, "from sample import OptionKey\nOptionKey" + WRITE),
    # The re-exporting binding is not unique, so the reference collector does not map it.
    "try-import": (
        {
            "sample/api.py": "try:\n    from .catalog import OptionKey\n"
            "except ImportError:\n    OptionKey = None\n"
        },
        "from .api import OptionKey\nOptionKey" + WRITE,
    ),
    "conditional-import": (
        {
            "sample/api.py": "import sys\nif sys.version_info >= (3,):\n"
            "    from .catalog import OptionKey\n"
        },
        "from .api import OptionKey\nOptionKey" + WRITE,
    ),
    "type-checking-else": (
        {
            "sample/api.py": "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
            "    from .catalog import OptionKey\nelse:\n    from .catalog import OptionKey\n"
        },
        "from .api import OptionKey\nOptionKey" + WRITE,
    ),
    "repeated-import": (
        {"sample/api.py": "from .catalog import OptionKey\nfrom .catalog import OptionKey\n"},
        "from .api import OptionKey\nOptionKey" + WRITE,
    ),
    "package-try-import": (
        {
            "sample/__init__.py": "try:\n    from .catalog import OptionKey\n"
            "except ImportError:\n    pass\n"
        },
        "from sample import OptionKey\nOptionKey" + WRITE,
    ),
    # A star import of the catalog module re-exports the owner under its own name.
    "star-reexport": (STAR_API, "from .api import OptionKey\nOptionKey" + WRITE),
    "package-star": (
        {"sample/__init__.py": "from .catalog import *\n"},
        "from sample import OptionKey\nOptionKey" + WRITE,
    ),
    "package-star-attribute": (
        {"sample/__init__.py": "from .catalog import *\n"},
        "import sample\nsample.OptionKey" + WRITE,
    ),
    "star-of-a-reexport": (
        {**API, "sample/api2.py": "from .api import *\n"},
        "from .api2 import OptionKey\nOptionKey" + WRITE,
    ),
    "star-two-hops": (
        {**STAR_API, "sample/api2.py": "from .api import *\n"},
        "from .api2 import OptionKey\nOptionKey" + WRITE,
    ),
    # The catalog module object itself, imported from a module that imports it.
    "module-object-reexport": (
        {"sample/api.py": "from . import catalog\n"},
        "from .api import catalog\ncatalog.OptionKey" + WRITE,
    ),
    # The catalog module object as an attribute of a module that holds it.
    "held-module-from-import": (MODULE_API, "from . import api\napi.catalog.OptionKey" + WRITE),
    "held-module-dotted-import": (
        MODULE_API,
        "import sample.api\nsample.api.catalog.OptionKey" + WRITE,
    ),
    "held-module-import-alias": (MODULE_API, "import sample.api as a\na.catalog.OptionKey" + WRITE),
    "held-module-under-alias": (
        {"sample/api.py": "from . import catalog as cat\n"},
        "from . import api\napi.cat.OptionKey" + WRITE,
    ),
    "held-package-of-module": (
        {"sample/api.py": "import sample.catalog\n"},
        "from . import api\napi.sample.catalog.OptionKey" + WRITE,
    ),
    "held-module-two-hops": (
        {**MODULE_API, "sample/api2.py": "from . import api\n"},
        "from . import api2\napi2.api.catalog.OptionKey" + WRITE,
    ),
    "star-of-a-holder": (
        {**MODULE_API, "sample/api2.py": "from .api import *\n"},
        "from .api2 import catalog\ncatalog.OptionKey" + WRITE,
    ),
    "held-module-in-package-init": (
        {"sample/sub/__init__.py": "from .. import catalog\n"},
        "from . import sub\nsub.catalog.OptionKey" + WRITE,
    ),
}


@pytest.mark.parametrize("form", REEXPORT_ESCAPES)
def test_owner_read_through_a_reexport_keeps_argument_unknown(tmp_path, form):
    files, other = REEXPORT_ESCAPES[form]
    verdict = _verdicts(
        tmp_path,
        caller=HEAD + CONSUME,
        rules=[_argument_rule()],
        extra_files={**files, "sample/other.py": other},
    )
    assert verdict == ("UNKNOWN", False)


def test_rebound_owner_import_in_a_reexporting_module_keeps_argument_unknown(tmp_path):
    # Sound but strict: `OptionKey` in api is not unique, so the check cannot tell which
    # value `api.OptionKey` holds and treats it as the owner.
    verdict = _verdicts(
        tmp_path,
        caller=HEAD + CONSUME,
        rules=[_argument_rule()],
        extra_files={
            "sample/api.py": "from .catalog import OptionKey, ExtraKey\nOptionKey = ExtraKey\n",
            "sample/other.py": "from . import api\napi.OptionKey('new')._value_ = 'x'\n",
        },
    )
    assert verdict == ("UNKNOWN", False)


@pytest.mark.parametrize(
    "other",
    [
        "from .api import OptionKey\ndef typed(value: OptionKey) -> None: ...\n",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .api import OptionKey\n"
        "def typed(value: 'OptionKey') -> None: ...\n",
    ],
    ids=["annotation", "type-checking"],
)
def test_owner_named_through_a_reexport_only_in_annotations_still_passes(tmp_path, other):
    verdict = _verdicts(
        tmp_path,
        caller=HEAD + CONSUME,
        rules=[_argument_rule()],
        extra_files={**API, "sample/other.py": other},
    )
    assert verdict == ("PASS", True)


def test_owner_named_only_in_annotations_elsewhere_still_passes(tmp_path):
    verdict = _verdicts(
        tmp_path,
        caller=HEAD + CONSUME,
        rules=[_argument_rule()],
        extra_files={
            "sample/other.py": HEAD + "def typed(value: OptionKey) -> OptionKey: ...\n"
            "LATEST: OptionKey | None = None\n"
        },
    )
    assert verdict == ("PASS", True)


def test_owner_call_through_a_star_import_keeps_argument_unknown(tmp_path):
    verdict = _verdicts(
        tmp_path,
        caller=HEAD + CONSUME,
        rules=[_argument_rule()],
        extra_files={
            "sample/other.py": "from .catalog import *\n"
            "def go():\n    OptionKey('page_size')._value_ = 'x'\n"
        },
    )
    assert verdict == ("UNKNOWN", False)


def test_owner_call_as_the_selected_argument_keeps_argument_unknown(tmp_path):
    caller = HEAD + "def consume():\n    read_option(OptionKey('page_size'))\n"
    assert _verdicts(tmp_path, caller=caller, rules=[_argument_rule()]) == ("UNKNOWN", False)


# --- (b) keyword argument evidence matches the member reference it contains ----------------

OPS = "def read_option(key: str) -> None: pass\n"
KEYWORD_ONLY_OPS = "def read_option(*, key: str) -> None: pass\n"
TWO_FORMAL_OPS = "def read_option(prefix: str, key: str) -> None: pass\n"
DEFAULT_OPS = "def read_option(key: str = 'bogus') -> None: pass\n"


def _call_verdict(tmp_path, operation: str, call: str, rule=None, **run_arguments):
    return _verdicts(
        tmp_path,
        caller=f"from .ops import read_option\nfrom .catalog import OptionKey, ExtraKey\n"
        f"def consume(opts, args):\n    {call}\n",
        rules=[rule or _argument_rule("sample.ops.read_option")],
        extra_files={"sample/ops.py": operation},
        **run_arguments,
    )


PASSING_CALLS = {
    "positional": (OPS, "read_option(OptionKey.PAGE_SIZE)"),
    "keyword": (OPS, "read_option(key=OptionKey.PAGE_SIZE)"),
    "keyword-spaced": (OPS, "read_option(key = OptionKey.PAGE_SIZE)"),
    "keyword-only-formal": (KEYWORD_ONLY_OPS, "read_option(key=OptionKey.PAGE_SIZE)"),
    "keyword-after-positional": (TWO_FORMAL_OPS, "read_option('p', key=OptionKey.PAGE_SIZE)"),
    "keyword-after-non-ascii": (TWO_FORMAL_OPS, "read_option('é', key=OptionKey.PAGE_SIZE)"),
    "keyword-before-other-keyword": (
        TWO_FORMAL_OPS,
        "read_option(key=OptionKey.PAGE_SIZE, prefix='p')",
    ),
    "keyword-valid-literal": (OPS, "read_option(key='page_size')"),
    "default-formal-omitted": (DEFAULT_OPS, "read_option()"),
}


@pytest.mark.parametrize("mounted", [False, True])
@pytest.mark.parametrize("case", PASSING_CALLS)
def test_catalog_argument_proves_the_call_forms_it_can_bind(tmp_path, case, mounted):
    operation, call = PASSING_CALLS[case]
    assert _call_verdict(tmp_path, operation, call, mounted=mounted) == ("PASS", True)


UNPROVEN_CALLS = {
    "keyword-plus-expression": (OPS, "read_option(key=OptionKey.PAGE_SIZE + 'x')"),
    "positional-plus-expression": (OPS, "read_option(OptionKey.PAGE_SIZE + 'x')"),
    "positional-member-attribute": (OPS, "read_option(OptionKey.PAGE_SIZE.value)"),
    "keyword-member-attribute": (OPS, "read_option(key=OptionKey.PAGE_SIZE.value)"),
    "keyword-parenthesized": (OPS, "read_option(key=(OptionKey.PAGE_SIZE))"),
    "keyword-unknown-member": (OPS, "read_option(key=OptionKey.MISSING)"),
    "keyword-other-owner": (OPS, "read_option(key=ExtraKey.NEW)"),
    "keyword-unknown-name": (OPS, "read_option(other=OptionKey.PAGE_SIZE)"),
    "keyword-dynamic": (OPS, "read_option(key=opts)"),
    "keyword-expansion-dynamic": (OPS, "read_option(**opts)"),
    "keyword-expansion-literal": (OPS, "read_option(**{'key': OptionKey.PAGE_SIZE})"),
    "star-dynamic": (OPS, "read_option(*args)"),
    "star-literal": (OPS, "read_option(*[OptionKey.PAGE_SIZE])"),
}


@pytest.mark.parametrize("case", UNPROVEN_CALLS)
def test_catalog_argument_keeps_unprovable_call_forms_unknown(tmp_path, case):
    operation, call = UNPROVEN_CALLS[case]
    assert _call_verdict(tmp_path, operation, call) == ("UNKNOWN", False)


def test_catalog_argument_still_reports_an_invalid_keyword_literal(tmp_path):
    assert _call_verdict(tmp_path, OPS, "read_option(key='bogus')") == ("FAIL", True)


def test_keyword_member_does_not_hide_an_escape_elsewhere(tmp_path):
    verdict = _verdicts(
        tmp_path,
        caller="from .ops import read_option\nfrom .catalog import OptionKey\n"
        "def consume():\n    read_option(key=OptionKey.PAGE_SIZE)\n",
        rules=[_argument_rule("sample.ops.read_option")],
        extra_files={
            "sample/ops.py": OPS,
            "sample/other.py": "from .catalog import OptionKey\n"
            + MUTATE
            + "def go():\n    mutate(OptionKey.PAGE_SIZE)\n",
        },
    )
    assert verdict == ("UNKNOWN", False)


@pytest.mark.parametrize(
    "call", ["read_option(key=OptionKey.PAGE_SIZE)", "read_option('page_size')"]
)
def test_catalog_use_counts_keyword_and_literal_reads_of_a_selected_operation(tmp_path, call):
    rule = _use(target="sample.ops.read_option", parameter="key", member="PAGE_SIZE")
    assert _call_verdict(tmp_path, OPS, call, rule=rule) == ("PASS", True)


def test_catalog_use_reports_a_member_no_keyword_call_reads(tmp_path):
    rule = _use(target="sample.ops.read_option", parameter="key", member="RETIRED")
    assert _call_verdict(tmp_path, OPS, "read_option(key=OptionKey.PAGE_SIZE)", rule=rule) == (
        "FAIL",
        True,
    )


# --- non-ASCII identifiers: Python allows them, and evidence columns count UTF-8 bytes ------

TWO_FORMAL_OPS_PREFIXED = "def read_option(prefix: str, key: str) -> None: pass\n"


def _alias_verdict(tmp_path, alias: str, statement: str, operation: str = OPS, **rule_changes):
    return _verdicts(
        tmp_path,
        caller=f"from .ops import read_option\nfrom .catalog import OptionKey as {alias}\n"
        f"def consume():\n    {statement}\n",
        rules=[{**_argument_rule("sample.ops.read_option"), **rule_changes}],
        extra_files={"sample/ops.py": operation},
    )


UNICODE_ALIAS_CALLS = {
    "ascii-positional": ("Keys", "read_option(Keys.PAGE_SIZE)", OPS),
    "ascii-keyword": ("Keys", "read_option(key=Keys.PAGE_SIZE)", OPS),
    "unicode-positional": ("Clé", "read_option(Clé.PAGE_SIZE)", OPS),
    "unicode-keyword": ("Clé", "read_option(key=Clé.PAGE_SIZE)", OPS),
    "unicode-after-multibyte-text": ("Clé", "result = ('é', read_option(Clé.PAGE_SIZE))", OPS),
    "unicode-keyword-after-multibyte-argument": (
        "Clé",
        "read_option('é', key=Clé.PAGE_SIZE)",
        TWO_FORMAL_OPS_PREFIXED,
    ),
    "unicode-alias-spaced": ("Clé", "read_option( Clé.PAGE_SIZE )", OPS),
}


@pytest.mark.parametrize("case", UNICODE_ALIAS_CALLS)
def test_catalog_argument_proves_members_reached_through_an_alias(tmp_path, case):
    alias, statement, operation = UNICODE_ALIAS_CALLS[case]
    assert _alias_verdict(tmp_path, alias, statement, operation) == ("PASS", True)


def test_catalog_argument_proves_a_keyword_for_a_non_ascii_formal(tmp_path):
    verdict = _alias_verdict(
        tmp_path,
        "Keys",
        "read_option(clé=Keys.PAGE_SIZE)",
        "def read_option(clé: str) -> None: pass\n",
        parameter="clé",
    )
    assert verdict == ("PASS", True)


def test_catalog_argument_proves_a_catalog_in_a_non_ascii_module(tmp_path):
    verdict = _verdicts(
        tmp_path,
        caller="from .ops import read_option\nfrom .café import OptionKey\n"
        "def consume():\n    read_option(OptionKey.PAGE_SIZE)\n",
        rules=[{**_argument_rule("sample.ops.read_option"), "catalog": "sample.café.OptionKey"}],
        extra_files={
            "sample/ops.py": OPS,
            "sample/café.py": "from enum import StrEnum\n"
            "class OptionKey(StrEnum):\n    PAGE_SIZE = 'page_size'\n",
        },
    )
    assert verdict == ("PASS", True)


def test_unicode_alias_member_in_a_selected_operation_call_elsewhere_is_accounted(tmp_path):
    verdict = _verdicts(
        tmp_path,
        caller=HEAD + CONSUME,
        rules=[_argument_rule()],
        extra_files={
            "sample/other.py": "from .catalog import OptionKey as Clé, read_option\n"
            "def go():\n    read_option(Clé.PAGE_SIZE)\n"
        },
    )
    assert verdict == ("PASS", True)


def test_unicode_alias_member_passed_elsewhere_is_an_escape(tmp_path):
    verdict = _verdicts(
        tmp_path,
        caller=HEAD + CONSUME,
        rules=[_argument_rule()],
        extra_files={
            "sample/other.py": "from .catalog import OptionKey as Clé\n"
            "def go():\n    print(Clé.PAGE_SIZE)\n"
        },
    )
    assert verdict == ("UNKNOWN", False)


@pytest.mark.parametrize("alias", ["\ufb01le", "Cle\u0301", "\U0001d40aeys"])
def test_catalog_argument_proves_an_alias_the_parser_normalises(tmp_path, alias):
    # Python reads identifiers in NFKC form: a ligature, a combining mark and a styled letter.
    assert _alias_verdict(tmp_path, alias, f"read_option({alias}.PAGE_SIZE)") == ("PASS", True)


@pytest.mark.parametrize(
    "annotation",
    ["Annotated[OptionKey, 'meta']", "list[OptionKey] | None", "'OptionKey'"],
)
def test_owner_in_an_annotation_without_a_call_still_passes(tmp_path, annotation):
    verdict = _verdicts(
        tmp_path,
        caller=HEAD + CONSUME,
        rules=[_argument_rule()],
        extra_files={
            "sample/other.py": HEAD
            + "from typing import Annotated\n"
            + f"def f(v: {annotation}) -> None: ...\n"
        },
    )
    assert verdict == ("PASS", True)

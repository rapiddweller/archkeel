# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Numeric alias proofs in PEP 695 scopes agree between collector and saved-facts reader (#618)."""

import json
import sys

import pytest

from archkeel.analyzer.python.collect import collect
from archkeel.ir.facts import stable_id
from archkeel.ir.facts_codec import (
    CollectionResponse,
    ProtocolError,
    decode_response,
    encode_response,
)
from archkeel.ir.protocol import CollectionRequest, PythonSettings, SnapshotInput, SourceScope

pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="PEP 695 syntax requires Python 3.12"
)

_PEP_696 = pytest.mark.skipif(
    sys.version_info < (3, 13), reason="type parameter defaults require Python 3.13"
)


def _payload(tmp_path, source):
    (tmp_path / "sample").mkdir(exist_ok=True)
    (tmp_path / "sample/core.py").write_text(source)
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    return json.loads(encode_response(CollectionResponse(facts)))


def _operation(payload):
    operations = [
        record
        for section in payload["facts"]["sections"]
        for record in section["records"]
        if record["kind"] == "numeric_operand"
    ]
    assert len(operations) == 1
    return operations[0]


def _decode(payload):
    return decode_response(json.dumps(payload).encode())


def _forge_known(payload, source, name, value, *, owner=None, local=False):
    """Claim a known alias proof for the one operation, as a hostile producer would."""
    operation = _operation(payload)
    rows = payload["facts"]["evidence"]
    assignment = next(row for row in rows if row["excerpt"].strip() == f"{name} = {value}")
    origin = {
        "name": name,
        "value": value,
        "expression": str(value),
        "evidence_id": assignment["id"],
        "line": assignment["line"],
        "column": assignment["column"],
        "end_line": assignment["end_line"],
        "end_column": assignment["column"] + len(assignment["excerpt"].strip()),
    }
    operation["evidence_ids"].append(assignment["id"])
    scopes = []
    if owner is not None:
        # The owner runs to the end of the file in these sources. An unknown proof can lack the
        # scope row, so the forgery adds it unless the collector wrote it.
        lines = source.splitlines()
        first = next(
            number
            for number, text in enumerate(lines, 1)
            if text.startswith((f"def {owner}", f"async def {owner}", f"class {owner}"))
        )
        scope_id = stable_id("EVD", "sample/core.py", first, len(lines), 0, "numeric_scope")
        if all(row["id"] != scope_id for row in rows):
            rows.append(
                {
                    "id": scope_id,
                    "file": "sample/core.py",
                    "line": first,
                    "end_line": len(lines),
                    "column": 0,
                    "excerpt": "\n".join(lines[first - 1 :]),
                }
            )
        symbol = next(
            record
            for section in payload["facts"]["sections"]
            for record in section["records"]
            if record["kind"] in {"function", "class"} and record["data"]["name"] == owner
        )
        scope = {
            "scope_owner": f"sample.core.{owner}",
            "scope_evidence_id": scope_id,
            "scope_symbol_id": symbol["id"],
        }
        if local:
            origin.update(scope)
        scopes = [scope]
        operation["evidence_ids"].append(scope_id)
    operation["data"].update(proof="known", value=value, derivation=[origin], binding_scopes=scopes)


def _drop_symbols(payload, names, *, prune_evidence):
    """Remove definition symbol records, the optional inventory the reader must not trust.

    With prune_evidence every other row that shows a generic header goes too, except the
    operation's own rows. Those cannot go: the reader needs them to replay the operation.
    """
    sections = payload["facts"]["sections"]
    dropped_ids = {
        record["id"]
        for section in sections
        for record in section["records"]
        if record["kind"] in {"function", "method", "class"} and record["data"]["name"] in names
    }
    for section in sections:
        section["records"] = [
            record
            for record in section["records"]
            if record["id"] not in dropped_ids
            and record["data"].get("declaration_id") not in dropped_ids
        ]
    if prune_evidence:
        own = set(_operation(payload)["evidence_ids"])
        gone = {
            row["id"]
            for row in payload["facts"]["evidence"]
            if row["excerpt"].lstrip().startswith(("def ", "async def ", "class "))
            and "[" in row["excerpt"]
            and row["id"] not in own
        }
        payload["facts"]["evidence"] = [
            row for row in payload["facts"]["evidence"] if row["id"] not in gone
        ]
        for section in sections:
            for record in section["records"]:
                record["evidence_ids"] = [i for i in record["evidence_ids"] if i not in gone]


# Collector -> encode -> decode: what the collector proves, the reader must replay.
_CAPTURED_LOCALS = [
    pytest.param(
        "def outer():\n    WIDTH = 7\n    type Alias[T] = nonce % WIDTH\n",
        "known",
        7,
        id="function",
    ),
    pytest.param(
        "async def outer():\n    WIDTH = 7\n    type Alias[T] = nonce % WIDTH\n",
        "known",
        7,
        id="async-function",
    ),
    pytest.param(
        "class K:\n    def m(self):\n        WIDTH = 7\n        type Alias[T] = nonce % WIDTH\n",
        "known",
        7,
        id="method",
    ),
    pytest.param(
        "class K:\n    async def m(self):\n        WIDTH = 7\n"
        "        type Alias[T] = nonce % WIDTH\n",
        "known",
        7,
        id="async-method",
    ),
    pytest.param(
        "def outer():\n    WIDTH = 7\n    class K:\n"
        "        def m(self):\n            type Alias[T] = nonce % WIDTH\n",
        "known",
        7,
        id="method-of-local-class",
    ),
    pytest.param(
        "def outer():\n    WIDTH = 7\n    class K:\n"
        "        async def m(self):\n            type Alias[T] = nonce % WIDTH\n",
        "known",
        7,
        id="async-method-of-local-class",
    ),
    pytest.param(
        "def outer():\n    WIDTH = 7\n    def inner():\n        type Alias[T] = nonce % WIDTH\n",
        "known",
        7,
        id="nested-function",
    ),
    pytest.param(
        "WIDTH = 4\ndef outer():\n    WIDTH = 7\n    type Alias[T] = nonce % WIDTH\n",
        "known",
        7,
        id="local-over-module",
    ),
    pytest.param(
        "WIDTH = 4\ndef outer():\n    type Alias[T] = nonce % WIDTH\n",
        "known",
        4,
        id="module-in-function",
    ),
    pytest.param(
        "def outer():\n    A = 3\n    type Alias[T] = nonce % A ** 2\n",
        "known",
        9,
        id="chained-power",
    ),
    pytest.param("WIDTH = 4\ntype Alias[T] = nonce % WIDTH\n", "known", 4, id="module-level"),
    # Brackets that do not open type parameters must not make a definition look generic.
    pytest.param(
        "WIDTH = 4\ndef f(x: list[int]):\n    return nonce % WIDTH\n",
        "known",
        4,
        id="subscript-annotation",
    ),
    pytest.param(
        "WIDTH = 4\nclass B: pass\nclass K(B[int]):\n    v = nonce % WIDTH\n",
        "known",
        4,
        id="subscript-base",
    ),
    pytest.param("WIDTH = 4\nclass K: v = [nonce % WIDTH]\n", "known", 4, id="one-line-class-list"),
    pytest.param(
        "WIDTH = 4\ndef f(x): return [nonce % WIDTH]\n", "known", 4, id="one-line-function-list"
    ),
    # A type parameter shadows the name, so the proof must stay unknown and still decode.
    pytest.param(
        "def outer():\n    WIDTH = 7\n    type Alias[WIDTH] = nonce % WIDTH\n",
        "unknown",
        None,
        id="tp-shadows-local",
    ),
    pytest.param(
        "WIDTH = 4\ndef outer():\n    type Alias[WIDTH] = nonce % WIDTH\n",
        "unknown",
        None,
        id="tp-shadows-module",
    ),
    pytest.param(
        "def outer():\n    A = 3\n    type Alias[B] = nonce % A ** B\n",
        "unknown",
        None,
        id="tp-shadows-one-name",
    ),
    pytest.param(
        "def outer[WIDTH]():\n    type Alias[T] = nonce % WIDTH\n",
        "unknown",
        None,
        id="outer-tp-shadows",
    ),
    pytest.param(
        "class K:\n    WIDTH = 7\n    type Alias[T] = nonce % WIDTH\n",
        "unknown",
        None,
        id="class-body-alias",
    ),
    # Generic definition scopes: the collector withholds the proof, except for decorators.
    pytest.param(
        "def outer():\n    WIDTH = 7\n    def g[T](x: nonce % WIDTH): pass\n",
        "unknown",
        None,
        id="local-annotation",
    ),
    pytest.param(
        "def outer():\n    WIDTH = 7\n    def g[T]() -> nonce % WIDTH: pass\n",
        "unknown",
        None,
        id="local-return",
    ),
    pytest.param(
        "def outer():\n    WIDTH = 7\n    def g[T](x=nonce % WIDTH): pass\n",
        "unknown",
        None,
        id="local-default",
    ),
    pytest.param(
        "def outer():\n    WIDTH = 7\n    def g[T](x):\n        return nonce % WIDTH\n",
        "unknown",
        None,
        id="local-body",
    ),
    pytest.param(
        "def outer():\n    WIDTH = 7\n    class K[T](B[nonce % WIDTH]): pass\n",
        "unknown",
        None,
        id="local-class-base",
    ),
    pytest.param(
        "def outer():\n    WIDTH = 7\n    def g[T: nonce % WIDTH](): pass\n",
        "unknown",
        None,
        id="local-type-bound",
    ),
    pytest.param(
        "def outer():\n    WIDTH = 7\n    @d(nonce % WIDTH)\n    def g[T](): pass\n",
        "known",
        7,
        id="local-decorator",
    ),
]


@pytest.mark.parametrize(("source", "proof", "value"), _CAPTURED_LOCALS)
def test_collected_numeric_proofs_replay_in_generic_scopes(tmp_path, source, proof, value):
    payload = _payload(tmp_path, source)
    operation = _operation(payload)
    assert (operation["data"]["proof"], operation["data"]["value"]) == (proof, value)
    _decode(payload)


@_PEP_696
@pytest.mark.parametrize(
    "source",
    [
        "WIDTH = 4\nclass K[T = nonce % WIDTH]: pass\n",
        "def outer():\n    WIDTH = 7\n    type Alias[T = nonce % WIDTH] = T\n",
    ],
)
def test_collected_type_parameter_defaults_stay_unknown_and_replay(tmp_path, source):
    payload = _payload(tmp_path, source)
    assert _operation(payload)["data"]["proof"] == "unknown"
    _decode(payload)


# Forged known proofs must be rejected even when the optional symbol inventory is gone.
_HEADERS = [
    pytest.param("def f[WIDTH](x: nonce % WIDTH): pass", id="function-annotation"),
    pytest.param("async def f[WIDTH](x: nonce % WIDTH): pass", id="async-annotation"),
    pytest.param("def f[WIDTH]() -> nonce % WIDTH: pass", id="return-annotation"),
    pytest.param("def f[WIDTH](x: int = nonce % WIDTH): pass", id="default"),
    pytest.param("def f[T: nonce % WIDTH](): pass", id="type-bound"),
    pytest.param("def f[T: (nonce % WIDTH)](): pass", id="type-bound-constraint"),
    pytest.param("class K[WIDTH](B[nonce % WIDTH]): pass", id="class-base"),
    pytest.param("class K[WIDTH](metaclass=B[nonce % WIDTH]): pass", id="class-keyword"),
]


@pytest.mark.parametrize("prune_evidence", [False, True], ids=["orphan-evidence", "no-evidence"])
@pytest.mark.parametrize("header", _HEADERS)
def test_forged_header_proof_is_rejected_without_symbol_records(tmp_path, header, prune_evidence):
    source = f"WIDTH = 4\nclass B: pass\n{header}\n"
    payload = _payload(tmp_path, source)
    assert _operation(payload)["data"]["proof"] == "unknown"
    _forge_known(payload, source, "WIDTH", 4)
    _drop_symbols(payload, {"f", "K"}, prune_evidence=prune_evidence)
    with pytest.raises(ProtocolError, match="unresolved type parameter"):
        _decode(payload)


@_PEP_696
@pytest.mark.parametrize("prune_evidence", [False, True], ids=["orphan-evidence", "no-evidence"])
def test_forged_type_parameter_default_proof_is_rejected_without_symbol_records(
    tmp_path, prune_evidence
):
    source = "WIDTH = 4\nclass K[T = nonce % WIDTH]: pass\n"
    payload = _payload(tmp_path, source)
    _forge_known(payload, source, "WIDTH", 4)
    _drop_symbols(payload, {"K"}, prune_evidence=prune_evidence)
    with pytest.raises(ProtocolError, match="unresolved type parameter"):
        _decode(payload)


@pytest.mark.parametrize(
    "source",
    [
        "WIDTH = 4\ndef f[WIDTH]() -> (\n    nonce % WIDTH\n): pass\n",
        "WIDTH = 4\nclass B: pass\nclass K[WIDTH](\n    B[nonce % WIDTH]\n): pass\n",
    ],
    ids=["function", "class"],
)
def test_forged_multiline_header_proof_is_rejected_without_symbol_records(tmp_path, source):
    payload = _payload(tmp_path, source)
    _forge_known(payload, source, "WIDTH", 4)
    _drop_symbols(payload, {"f", "K"}, prune_evidence=False)
    with pytest.raises(ProtocolError, match="unresolved type parameter"):
        _decode(payload)


def test_forged_header_of_a_nested_generic_definition_is_rejected(tmp_path):
    source = "def outer():\n    W = 7\n    def g[W](x: nonce % W): pass\n"
    payload = _payload(tmp_path, source)
    _forge_known(payload, source, "W", 7, owner="outer", local=True)
    _drop_symbols(payload, {"g"}, prune_evidence=True)
    with pytest.raises(ProtocolError, match="unresolved type parameter"):
        _decode(payload)


def test_forged_local_proof_through_a_shadowing_type_parameter_is_rejected(tmp_path):
    # The multiline alias hides its header from the one-line evidence: only the owner excerpt
    # still shows that the type parameter W shadows the local W.
    source = (
        "def outer():\n    W = 7\n    type Alias[\n        W\n    ] = (\n        nonce % W\n    )\n"
    )
    payload = _payload(tmp_path, source)
    _forge_known(payload, source, "W", 7, owner="outer", local=True)
    kept = [
        row
        for row in payload["facts"]["evidence"]
        if not row["excerpt"].lstrip().startswith("type ")
    ]
    kept_ids = {row["id"] for row in kept}
    payload["facts"]["evidence"] = kept
    for section in payload["facts"]["sections"]:
        for record in section["records"]:
            record["evidence_ids"] = [i for i in record["evidence_ids"] if i in kept_ids]
    with pytest.raises(ProtocolError, match="complete source witness"):
        _decode(payload)


# The collector proves only a generic alias value inside a function. It withholds the alias
# bounds and defaults and an alias that sits directly in a class body, so the reader must too.
@pytest.mark.parametrize(
    ("source", "name", "value", "owner", "local"),
    [
        pytest.param(
            "def outer():\n    W = 7\n    type A[T: (nonce % W)] = T\n",
            "W",
            7,
            "outer",
            True,
            id="local-type-bound",
        ),
        pytest.param(
            "WIDTH = 4\ndef outer():\n    type A[T: (nonce % WIDTH)] = T\n",
            "WIDTH",
            4,
            "outer",
            False,
            id="module-type-bound",
        ),
        pytest.param(
            "class K:\n    W = 7\n    type Alias[T] = nonce % W\n",
            "W",
            7,
            "K",
            True,
            id="local-class-body-alias",
        ),
        pytest.param(
            "WIDTH = 4\nclass K:\n    type Alias[T] = nonce % WIDTH\n",
            "WIDTH",
            4,
            "K",
            False,
            id="module-class-body-alias",
        ),
    ],
)
def test_reader_withholds_what_the_collector_withholds_in_generic_aliases(
    tmp_path, source, name, value, owner, local
):
    payload = _payload(tmp_path, source)
    assert _operation(payload)["data"]["proof"] == "unknown"
    _forge_known(payload, source, name, value, owner=owner, local=local)
    with pytest.raises(ProtocolError):
        _decode(payload)


@_PEP_696
def test_reader_withholds_type_parameter_defaults_in_generic_aliases(tmp_path):
    source = "def outer():\n    W = 7\n    type A[T = nonce % W] = T\n"
    payload = _payload(tmp_path, source)
    assert _operation(payload)["data"]["proof"] == "unknown"
    _forge_known(payload, source, "W", 7, owner="outer", local=True)
    with pytest.raises(ProtocolError):
        _decode(payload)

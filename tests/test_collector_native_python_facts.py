# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source fact dump boundaries, compared with the unchanged Python functions (AD-412)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest
from first_difference import same
from python_source_facts import aliases, lexical, parsed, state, state_inputs, typing_signals
from archkeel.analyzer.python.source import add_evidence
from test_collector_native_python_parse import _minor


@pytest.fixture(scope="session")
def facts_binary() -> Path:
    root = Path(__file__).parents[1]
    subprocess.run(["cargo", "build", "--locked", "-p", "archkeel-python-collector",
                    "--features", "dump", "--target-dir", "target/dump"],
                   cwd=root / "native", check=True, capture_output=True, text=True)
    return root / "native/target/dump/debug/archkeel-python-collector"


def native(binary: Path, root: Path, flag: str, request: dict[str, Any]) -> dict[str, Any]:
    result = subprocess.run(
        [str(binary), flag, str(_minor()), str(root)],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        timeout=10,
        check=True,
    )
    return json.loads(result.stdout)


def test_lexical_dump_exists(tmp_path: Path, facts_binary: Path) -> None:
    (tmp_path / "probe.py").write_text("x = 1\ndef f(a): return a + x\n")
    row = native(facts_binary, tmp_path, "--dump-lexical", {"file": "probe.py"})
    assert row["full_scope"], row
    assert row["data"]["names"]
    module = parsed(tmp_path, "probe.py")
    assert module is not None
    compare(row["data"], lexical(module), "lexical dump")


def compare(found: object, expected: object, label: object) -> None:
    same(json.dumps(found, sort_keys=True, ensure_ascii=False),
         json.dumps(expected, sort_keys=True, ensure_ascii=False), label)


def exact_cost(row: dict[str, Any], group: str, index: int) -> None:
    costs = json.loads(Path(__file__).with_name("python_fact_costs.json").read_text())
    assert row["work"] == costs[group][index], (group,index)


LEXICAL = (
    "class ___:\n __x=1\n def f(self,__p): return __p\n",
    "def f():\n x=1\n if ok:\n  def g(y): return x,y\n return g\n",
    "def outer():\n T=1\n def middle():\n  a: T\n  return T\n return middle\n",
    "class C:\n def f(self):\n  self = other\n  return self.x\n @decorator\n def g(self): return self.x\n def h(): return 1\n",
    "from x import C\nif guard:\n class C: pass\nx = C\n",
    "def f():\n global x\n class C:\n  x=1\n  def g(self): return x\n return C\n",
    "class C:\n __x=1\n def __f(self, __p):\n  __a=__p\n  return self.__x, __a\n",
    "x = 1\ndef f(a):\n global x\n x = a\n return x\n",
    "x = 1\ndef outer():\n x = 2\n def inner():\n  nonlocal x\n  x += 1\n  return x\n return inner\n",
    "x = 1\nclass C:\n print(x)\n x = 2\n def f(self, y): return self.x + y\n",
    "a = [x+y for x in xs for y in ys if y]\nb = {x for x in xs}\nc = {x:y for x,y in pairs}\nd = (x for x in xs)\n",
    "def f(xs):\n y = 0\n z = [(y := x) for x in xs]\n return y\n",
    "class C:\n x = 2\n y = [x for a in xs]\n",
    "def f(x):\n match x:\n  case {'x': y, **rest}: return y, rest\n  case [a, *b]: return a,b\n",
    "try:\n import os.path as path\nexcept ValueError as error:\n path = error\nx = path\n",
    "def f(a=1, /, b: int=2, *args: int, c: str='x', **kw: int) -> int:\n return a\n",
    "from pkg import x\nfrom pkg import x\ndef f():\n from other import x\n return x\n",
    "from pkg import *\nx\n",
    "def f():\n x = 1\n class C:\n  x = 2\n  def g(self): return x\n return C\n",
    "def f():\n x = 1\n return lambda y=x: y+x\n",
    "from __future__ import annotations\ndef f():\n x=1\n def g(y: x): return y\n return g\n",
    "def f(xs):\n return [[(x,y) for y in ys] for x in xs]\n",
    "async def f(xs):\n async for x in xs:\n  await x\n",
)


@pytest.mark.parametrize("index", range(len(LEXICAL)))
@pytest.mark.parametrize("with_aliases", (False, True))
def test_lexical_probe(index: int, with_aliases: bool, tmp_path: Path,
                       facts_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(LEXICAL[index])
    module = parsed(tmp_path, "probe.py")
    assert module is not None
    request: dict[str, Any] = {"file": "probe.py"}
    if with_aliases:
        request["aliases"] = aliases(module)
    row = native(facts_binary, tmp_path, "--dump-lexical", request)
    assert row["full_scope"], row
    compare(row["data"], lexical(module), index)
    exact_cost(row,"lexical",index*2+int(with_aliases))


GENERIC = (
    "T=1\ndef f[T](x: T=7%2) -> T:\n return x\n",
    "T=1\nclass C[T](Base[T], flag=T):\n def f(self, x:T): return T,x\n",
    "T=1\ntype A[T] = list[T] | Other\n",
    "class C:\n T=1\n type A[T] = tuple[T, Other]\n",
    "type A = Other\n",
)


@pytest.mark.requires_python(12)
@pytest.mark.parametrize("text", GENERIC)
def test_generic_lexical(text: str, tmp_path: Path, facts_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(text)
    module = parsed(tmp_path, "probe.py")
    assert module is not None
    row = native(facts_binary, tmp_path, "--dump-lexical", {"file": "probe.py"})
    assert row["full_scope"], row
    compare(row["data"], lexical(module), "generic scope")
    exact_cost(row,"generic",GENERIC.index(text))


TYPING = (
    "x: Any\ny: dict[str, Any]\nz: Callable[[Any], object]\nw: object\n",
    "class C:\n x: object\n def f(self, x: Any, /, y: Dict[str,Any], *a: Any, z: object, **kw: Any) -> Any:\n  self.x: dict[str, Any]\n  a[0]: object\n",
    "# type: ignore [module]\nx=1 # type: ignore[attr-defined]\n",
    "x=(\n 1+2 # type: ignore[arg-type]\n)\n",
    "x=1; y=2 # type: ignore[assignment]\n",
    "def f():\n return 1 # type: ignore[return-value]\n",
    "é = 1 # type: ignore[x]\n",
    "x: 'Any'\nx: typing.Callable[..., Any]\nx: typing.Dict[str, Any]\n",
    "from a import b # type: ignore\nimport a as c # type: ignore\n",
    "x: int = 1 # type: ignore\nx+=1 # type: ignore\ndel x # type: ignore\n",
)


@pytest.mark.parametrize("text", TYPING)
def test_typing_probe(text: str, tmp_path: Path, facts_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(text)
    module = parsed(tmp_path, "probe.py")
    assert module is not None
    inputs = {"file": "probe.py"}
    row = native(facts_binary, tmp_path, "--dump-typing-signals", inputs)
    assert row["full_scope"], row
    compare(row["data"], typing_signals(module, inputs), "typing probe")
    exact_cost(row,"typing",TYPING.index(text))


STATE = (
    "class C:\n x: Final[list[int]]\n def __init__(self, /, x: int):\n  self.a: dict[str,int] = {}\n  self.x = []\n def f(self):\n  self.x.append(1)\n  self.a = {}\n  del self.a\n",
    "class C:\n @property\n def x(self): return self._x\n @x.setter\n def x(self,v): self._x=v\n @property\n def y(self): return 1\n",
    "def f(a, /, b: int, *args, c: str, **kw):\n x = C(a, arg=b)\n y: int = x\n x,y = pair\n x.a.b.append(a)\n fn(x,a.b)\n getattr(x,'a')\n",
    "class A:\n class B:\n  def f(self):\n   def nested(x): return self.a, x\n   return nested\ndef outer():\n def inner(x): return x.a\n return inner\n",
    "async def f(self, x: Any):\n self.a += 1\n await self.a.fn(x)\n return factory().a\n",
)


@pytest.mark.parametrize("text", STATE)
@pytest.mark.parametrize("flags", ((False,False),(True,False),(False,True),(True,True)))
def test_state_probe(text: str, flags: tuple[bool,bool], tmp_path: Path, facts_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(text)
    module = parsed(tmp_path, "probe.py")
    assert module is not None
    inputs = state_inputs(module, *flags)
    row = native(facts_binary, tmp_path, "--dump-state", inputs)
    assert row["full_scope"], row
    compare(row["data"], state(module, inputs), "state probe")
    exact_cost(row,"state",STATE.index(text)*4+((False,False),(True,False),(False,True),(True,True)).index(flags))


def record_inputs(module: Any) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    evidence_id = add_evidence(evidence, module, module.tree.body[0])
    calls = [{"id": f"CALL-{i:016x}", "evidence_ids": [evidence_id, "EV-missing"],
              "data": {"expression": "dynamic(x)", "source_scope": "probe.f", "targets": targets}}
             for i, targets in enumerate(([], ["other"], ["typing.cast"], ["typing_extensions.cast"],
                                         ["builtins.getattr"], ["builtins.hasattr"], ["builtins.eval"],
                                         ["builtins.exec"], ["builtins.__import__"],
                                         ["importlib.import_module", "typing.cast"]))]
    imports = [{"data": {"source_package": source, "target_package": target,
                         "target_module": "lib.api", "symbol": symbol}}
               for source,target,symbol in (("probe","lib","f"),("probe","lib","g"),
                                             ("probe","lib","C"),("probe","lib","missing"),
                                             ("probe","probe","local"),("probe","lib",None))]
    symbols = [{"id": f"SYM-{i:016x}", "evidence_ids": [evidence_id],
                "data": {"qualified_name": name, "symbol_category": kind,
                         "parameters": params, "returns": returns}}
               for i,(name,kind,params,returns) in enumerate((
                   ("lib.api.f","function",[{"name":"z","annotation":None},
                                             {"name":"a","annotation":"int"}], None),
                   ("lib.api.g","method",[{"name":"x","annotation":"int"}], "str"),
                   ("lib.api.C","class",[],None)))]
    return {"file": "probe.py", "evidence": list(evidence.values()), "calls": calls,
            "symbols": symbols, "imports": imports}


def test_record_input_signals(tmp_path: Path, facts_binary: Path) -> None:
    (tmp_path / "probe.py").write_text("x: Any\n")
    module = parsed(tmp_path,"probe.py")
    assert module is not None
    inputs = record_inputs(module)
    row = native(facts_binary,tmp_path,"--dump-typing-signals",inputs)
    assert row["full_scope"], row
    compare(row["data"], typing_signals(module, inputs), "record inputs")
    exact_cost(row,"records",0)


def pair_source(index: int) -> str:
    text = LEXICAL[index%8] + LEXICAL[8+index//8]
    future = "from __future__ import annotations\n"
    return (future if future in text else "") + text.replace(future,"")


@pytest.mark.parametrize("index", range(64))
def test_generated_lexical_pair(index: int, tmp_path: Path, facts_binary: Path) -> None:
    (tmp_path / "probe.py").write_text(pair_source(index))
    module = parsed(tmp_path,"probe.py")
    assert module is not None
    row = native(facts_binary,tmp_path,"--dump-lexical",{"file":"probe.py","aliases":aliases(module)})
    assert row["full_scope"], row
    compare(row["data"],lexical(module),index)
    exact_cost(row,"pairs",index)


@pytest.mark.parametrize("boundary", ("lexical", "typing-signals", "state"))
def test_source_fact_budget(boundary: str, tmp_path: Path, facts_binary: Path) -> None:
    (tmp_path / "probe.py").write_text("def f(a: Any):\n return a.x\n")
    request = {"file": "probe.py"}
    row = native(facts_binary,tmp_path,f"--dump-{boundary}",request)
    assert row["full_scope"], row
    cost = row["work"]
    for limit, complete in ((cost,True),(cost-1,False),(0,False)):
        limited = native(facts_binary,tmp_path,f"--dump-{boundary}",{**request,"work_limit":limit})
        assert limited["full_scope"] is complete
        if not complete:
            assert limited["gap"] and "data" not in limited


@pytest.mark.parametrize("boundary", ("lexical", "typing-signals", "state"))
@pytest.mark.parametrize("raw", (
    b"x=" + b"(" * 5000 + b"1" + b")" * 5000,
    b"x='" + b"a" * 1_000_000 + b"'\n",
    b"x=1\n" * 100_000,
    b"x=1\x00\n",
    b"x='\xff'\n",
))
def test_hostile_source_fact(boundary: str, raw: bytes, tmp_path: Path, facts_binary: Path) -> None:
    (tmp_path / "probe.py").write_bytes(raw)
    start = perf_counter()
    row = native(facts_binary,tmp_path,f"--dump-{boundary}",{"file":"probe.py"})
    print("hostile source fact", _minor(), boundary, len(raw), perf_counter()-start, row.get("gap"))
    if not row["full_scope"]:
        assert row["gap"] and "data" not in row


@pytest.mark.parametrize("boundary", ("lexical", "typing-signals", "state"))
def test_source_fact_work_scaling(boundary: str, tmp_path: Path, facts_binary: Path) -> None:
    work = []
    times = []
    for size in (1000,3000):
        (tmp_path / "probe.py").write_text("".join(
            f"class C{i}:\n x: Any\n def f(self,a): return a.x\n" for i in range(size)))
        module = parsed(tmp_path,"probe.py")
        assert module is not None
        inputs = state_inputs(module) if boundary == "state" else {"file":"probe.py"}
        start = perf_counter()
        row = native(facts_binary,tmp_path,f"--dump-{boundary}",inputs)
        times.append(perf_counter()-start)
        assert row["full_scope"], row.get("gap")
        work.append(row["work"])
    print("source fact scaling", _minor(), boundary, work, times)
    assert 2.8 < work[1]/work[0] < 3.2


@pytest.mark.skipif(not os.environ.get("ARCHKEEL_FACT_CORPORA"), reason="no corpus is named")
@pytest.mark.parametrize("boundary", ("lexical", "typing-signals", "state"))
def test_source_fact_corpus(boundary: str, facts_binary: Path) -> None:
    public = os.environ["ARCHKEEL_FACT_CORPORA"].split(os.pathsep)
    private_roots = os.environ.get("ARCHKEEL_FACT_PRIVATE_CORPORA", "").split(os.pathsep)
    observations = {}
    for number, directory in enumerate([*public, *(p for p in private_roots if p)]):
        root = Path(directory)
        private = number >= len(public)
        label = "private aggregate" if private else f"{root.name}:{'repo' if (root / 'repo').is_dir() else 'direct'}"
        paths = sorted(p for p in root.rglob("*.py")
                       if p.is_file() and not p.is_symlink() and ".venv" not in p.parts)
        assert paths, "source fact corpus has no Python files"
        counts: dict[str, int] = {}
        different = []
        gaps = []
        maximum_work = 0
        with subprocess.Popen(
            [str(facts_binary), f"--dump-{boundary}", str(_minor()), str(root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        ) as process:
            assert process.stdin is not None and process.stdout is not None
            for path in paths:
                rel = str(path.relative_to(root))
                module = parsed(root, rel)
                request: dict[str, Any] = {"file": rel}
                if module is not None and boundary == "lexical":
                    request["aliases"] = aliases(module)
                if module is not None and boundary == "state":
                    request = state_inputs(module)
                process.stdin.write(json.dumps(request) + "\n")
                process.stdin.flush()
                row = json.loads(process.stdout.readline())
                maximum_work = max(maximum_work, row["work"])
                if module is None:
                    kind = "shared refusal" if not row["full_scope"] else "different parse"
                elif not row["full_scope"]:
                    kind = row["gap"]
                    gaps.append([kind, "private aggregate" if private else rel])
                else:
                    expected = (lexical(module) if boundary == "lexical" else
                                typing_signals(module, request) if boundary == "typing-signals" else
                                state(module, request))
                    kind = "equal" if canonical(row["data"]) == canonical(expected) else "different"
                    if kind == "different" and len(different) < 5:
                        different.append("private aggregate" if private else rel)
                counts[kind] = counts.get(kind, 0) + 1
            process.stdin.close()
            assert process.wait(timeout=30) == 0
        print("source fact corpus", _minor(), boundary, number, counts, different, "maximum work", maximum_work, flush=True)
        observations[label] = {"counts": counts, "gaps": sorted(gaps), "maximum_work": maximum_work}
        if report := os.environ.get("ARCHKEEL_FACT_REPORT"):
            with Path(report).open("a") as stream:
                stream.write(json.dumps({"minor": _minor(), "boundary": boundary, "label": label,
                                         **observations[label]}) + "\n")
        assert not any(key.startswith("different") for key in counts), different


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()

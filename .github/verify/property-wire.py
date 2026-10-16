import json
import sys
from pathlib import Path

root, fixture_root, output = map(Path, sys.argv[1:])
sys.path.insert(0, str(root.resolve() / "src"))
from archkeel.analyzer.python.collect import collect
from archkeel.ir.facts_codec import decode_response, encode_response
from archkeel.ir.protocol import (
    CollectionRequest, CollectionResponse, PythonSettings, SnapshotInput, SourceScope,
)

base = (
    "class Base:\n"
    "    @property\n    def value(self) -> int: ...\n"
    "    @value.setter\n    def value(self, value: int) -> None:\n        self._value = value\n"
    "class Child(Base):\n    pass\n"
)
sources = [
    base,
    base.replace("value: int", "value: object"),
    base.replace("class Child(Base):\n    pass\n",
                 "class Child(Base):\n    @Base.value.getter\n    def value(self) -> int: ...\n"),
    base.replace("@property", "@custom"),
    base.replace("class Child(Base):", "Base.value = custom\nclass Child(Base):"),
    base.replace("class Base:\n", "class Base:\n    @property\n    def value(self) -> str: ...\n", 1),
]
outputs = []
for index, source in enumerate(sources):
    fixture = fixture_root / str(index)
    (fixture / "sample").mkdir(parents=True, exist_ok=True)
    (fixture / "sample/__init__.py").write_text("")
    (fixture / "sample/api.py").write_text(source)
    (fixture / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    request = CollectionRequest(SnapshotInput(str(fixture.resolve()), "a" * 40, False),
                                SourceScope(("sample",), "sample"), PythonSettings())
    payload = encode_response(CollectionResponse(collect(request)))
    assert encode_response(decode_response(payload)) == payload
    value = json.loads(payload)
    # Only code provenance changes when the collector implementation changes.
    value["facts"]["adapter"]["code_digest"] = "<implementation>"
    outputs.append(value)
output.write_text(json.dumps(outputs, sort_keys=True, separators=(",", ":")))
print(f"PROPERTY_CANONICAL_WIRE_FIXTURES={len(outputs)}")

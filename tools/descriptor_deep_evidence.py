import json,sys,subprocess,collections,tempfile
from pathlib import Path
base=Path(sys.argv[1]);head=Path.cwd();probe=Path(__file__).with_name("descriptor_deep_probe.py")
folder=Path(tempfile.mkdtemp(prefix="descriptor-evidence-"));fixtures=folder/"fixtures"
files={
"python/pyproject.toml":'[project]\nrequires-python = ">=3.11"\n',
"python/sample/__init__.py":"",
"python/sample/api.py":'from abc import abstractmethod\nfrom typing import overload\nfrom builtins import classmethod as method\nclass Base:\n    @property\n    def value(self) -> int: ...\n    @value.setter\n    def value(self, new_value: int) -> None: ...\nclass Child(Base):\n    def instance(self, value: int) -> int: ...\n    @staticmethod\n    def static(value: int) -> int: ...\n    @classmethod\n    def kind(cls, value: int) -> int: ...\n    @staticmethod\n    @property\n    def static_property(value: int) -> int: ...\n    @property\n    @staticmethod\n    def property_static(value: int) -> int: ...\n    @classmethod\n    @staticmethod\n    def class_static(value: int) -> int: ...\n    @staticmethod\n    @classmethod\n    def static_class(value: int) -> int: ...\n    @method\n    @abstractmethod\n    def alias_abstract(cls, value: int) -> int: ...\n    @overload\n    def transparent(self, value: int) -> int: ...\n    @staticmethod()\n    def called(self, value: int) -> int: ...\n    @custom\n    def custom(self, value: int) -> int: ...\n',
"dart/pubspec.yaml":"name: app\nenvironment:\n  sdk: '>=3.9.0 <4.0.0'\n",
"dart/lib/api.dart":"class Child { Child(); factory Child.make() => Child(); static int build(int value) => value; int instance(int value) => value; }\n",
"typescript/tsconfig.json":json.dumps({"compilerOptions":{"module":"NodeNext","moduleResolution":"NodeNext"},"include":["src"]}),
"typescript/package.json":json.dumps({"name":"app","version":"1.0.0","type":"module"}),
"typescript/src/api.ts":"export class Child { static build(value: number): number { return value; } instance(value: number): number { return value; } }\n",
}
for path,text in files.items():
    p=fixtures/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
outputs={}
for name,root in (("base",base),("head",head)):
    native=folder/(name+"-native.json");wire=folder/(name+"-wire.json")
    subprocess.run([sys.executable,"-I",str(probe),"wire",str(root),str(fixtures),str(wire)],check=True)
    subprocess.run([sys.executable,"-I",str(probe),"native",str(root),str(native)],check=True)
    outputs[name]=(json.loads(native.read_text()),json.loads(wire.read_text()))
assert outputs["base"][1]==outputs["head"][1],"full normalized Python/Dart/TypeScript wire differs"
for name,payload in outputs["head"][1].items():
    kinds=collections.Counter(row["data"].get("method_kind") for section in payload["facts"]["sections"] for row in section["records"] if row["kind"]=="method")
    print("WIRE_EQUAL",name,dict(kinds))
def counter(rows):return collections.Counter(json.dumps(row,sort_keys=True) for row in rows)
for section in ("calls","references","unknowns"):
    left,right=(counter(outputs[name][0][section]) for name in ("base","head"))
    print("NATIVE_SECTION",section,"BASE",len(outputs["base"][0][section]),"HEAD",len(outputs["head"][0][section]))
    if section in ("calls","references"):
        for version in ("base","head"):
            statuses=collections.Counter(row["status"] for row in outputs[version][0][section])
            print("NATIVE_STATUS",section,version,dict(statuses))
    for label,delta in (("REMOVED",left-right),("ADDED",right-left)):
        for row,count in delta.items():print("NATIVE_DELTA",section,label,count,row)

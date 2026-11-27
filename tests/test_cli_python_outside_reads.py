# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1963: a file outside the scan holds the symbol records only for a use that can write.

A read of the version, of the package files, of a spec against `None` or of the names in
`sys.modules` gives no module object. A write, a subscript or any other use keeps the hold.
Each plant that writes is run with Python: the counter text proves that the scanned code changed.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from test_cli_native_python_imports import verdict
from test_cli_python_outside_withheld import statuses, tree

CLIENT = "from app.service import f\n\n\ndef run() -> str:\n    return f()\n"
SERVICE = 'def f() -> str:\n    return "orig"\n'

ABSENT = f"archkeel_absent_{uuid.uuid4().hex}"

READS = f"""\
import importlib.metadata
import importlib.resources
import importlib.util
import sys

import app.client

try:
    version = importlib.metadata.version("app")
except importlib.metadata.PackageNotFoundError:
    version = ""
assert importlib.util.find_spec("{ABSENT}") is None
assert "{ABSENT}" not in sys.modules
assert not any(name.startswith("zzz") for name in sys.modules)
package = importlib.resources.files("app")
print(app.client.run())
"""

# A hook that rewrites the file of the scanned module: only the plant can lead to the write.
HOOK = (
    "import pathlib\n\n\nclass Hook:\n    def __eq__(self, other):\n"
    "        self.version(other)\n        return False\n\n    def version(self, name):\n"
    '        pathlib.Path("src/app/service.py").write_text(\n'
    "            \"def f():\\n    return 'hooked'\\n\"\n        )\n"
    '        return "1"\n\n\n'
)

NEW_SOURCE = "def f():\n    return 'hooked'\n"

WRITES = {
    "files of a joined name": (
        "import importlib.resources\n"
        'importlib.resources.files("".join(["ap", "p"])).joinpath("service.py").write_text(NEW)\n'
        "import app.client\nprint(app.client.run())\n"
    ),
    "files of a decoded name": (
        "import importlib.resources\n"
        'importlib.resources.files(b"app".decode()).joinpath("service.py").write_text(NEW)\n'
        "import app.client\nprint(app.client.run())\n"
    ),
    "files of an f-string": (
        "import importlib.resources\n"
        'importlib.resources.files(f"app").joinpath("service.py").write_text(NEW)\n'
        "import app.client\nprint(app.client.run())\n"
    ),
    "subscript write": (
        'import sys\nimport app.service\nsys.modules["app.service"].f = lambda: "hooked"\n'
        "import app.client\nprint(app.client.run())\n"
    ),
    "replaced module": (
        "import sys\nimport types\n\nfake = types.ModuleType('app.service')\n"
        "fake.f = lambda: 'hooked'\nsys.modules['app.service'] = fake\nimport app.client\n"
        "print(app.client.run())\n"
    ),
    "get then write": (
        "import sys\nimport app.service\nsys.modules.get('app.service').f = lambda: 'hooked'\n"
        "import app.client\nprint(app.client.run())\n"
    ),
    "namespace through dict": (
        "import sys\nimport app.service\n"
        'sys.__dict__["modules"]["app.service"].f = lambda: "hooked"\n'
        "import app.client\nprint(app.client.run())\n"
    ),
    "namespace through vars": (
        "import sys\nimport app.service\n"
        'vars(sys)["modules"]["app.service"].f = lambda: "hooked"\n'
        "import app.client\nprint(app.client.run())\n"
    ),
    "namespace in a name": (
        'import sys\nimport app.service\nloaded = sys.modules\nloaded["app.service"].f = '
        'lambda: "hooked"\nimport app.client\nprint(app.client.run())\n'
    ),
    "walk then subscript": (
        "import sys\nimport app.service\nfor name in sys.modules:\n    if name == 'app.service':\n"
        "        sys.modules[name].f = lambda: 'hooked'\nimport app.client\n"
        "print(app.client.run())\n"
    ),
    "membership chain": (
        "import sys\nimport app.service\n\n\nclass Sink:\n"
        "    def __contains__(self, modules):\n"
        '        modules["app.service"].f = lambda: "hooked"\n'
        "        return True\n\n\n"
        '_ = "app.service" in sys.modules in Sink()\nimport app.client\n'
        "print(app.client.run())\n"
    ),
    "class attribute holds the path": (
        "import importlib.resources\n\n\nclass K:\n"
        '    p = importlib.resources.files("app")\n\n\n'
        'K.p.joinpath("service.py").write_text(NEW)\n'
        "import app.client\nprint(app.client.run())\n"
    ),
    "files through __import__": (
        '__import__("importlib.resources").resources.files("app")'
        '.joinpath("service.py").write_text(NEW)\n'
        "import app.client\nprint(app.client.run())\n"
    ),
    "plain open next to a read": (
        'import importlib.metadata\n\ntry:\n    importlib.metadata.version("app")\n'
        "except importlib.metadata.PackageNotFoundError:\n    pass\n"
        'with open("src/app/service.py", "w") as handle:\n    handle.write(NEW)\n'
        "import app.client\nprint(app.client.run())\n"
    ),
    "read compared with an object": (
        HOOK + "import importlib.metadata\n\ntry:\n"
        '    same = importlib.metadata.version("app") == Hook()\n'
        "except importlib.metadata.PackageNotFoundError:\n"
        "    same = Hook() == 1\nimport app.client\nprint(app.client.run())\n"
    ),
    "print to an object": (
        HOOK + "import importlib.metadata\n\n\nclass Out:\n    def write(self, text):\n"
        "        Hook().version(text)\n        return len(text)\n\n\n"
        "try:\n    importlib.metadata.version('app')\n"
        "except importlib.metadata.PackageNotFoundError:\n"
        "    pass\nprint('x', file=Out())\nimport app.client\nprint(app.client.run())\n"
    ),
    "imported module attribute": (
        "import app.service\napp.service.f = lambda: 'hooked'\nimport app.client\n"
        "print(app.client.run())\n"
    ),
}

# The hold stays, and no effect is shown: the use can give a module object or load by name.
HELD = {
    "entry points": (
        "import importlib.metadata\nimportlib.metadata.entry_points(group='app.service')\n"
    ),
    "spec used": (
        "import importlib.util\nspec = importlib.util.find_spec('app.service')\nprint(spec.name)\n"
    ),
    "alias": "import importlib.util as util\nprint(util.find_spec('app.service') is None)\n",
    "module values": "import sys\nprint('app.service', list(sys.modules.values()))\n",
}


def run(root: Path, script: str) -> str:
    (root / "scripts").mkdir(exist_ok=True)
    path = root / "scripts/tool.py"
    path.write_text(script.replace("NEW", repr(NEW_SOURCE)))
    env = {"PYTHONPATH": str(root / "src"), "PATH": ""}
    done = subprocess.run(
        [sys.executable, str(path)], capture_output=True, text=True, env=env, cwd=root
    )
    return done.stdout.strip() if done.returncode == 0 else done.stderr.strip()


def check(
    release_core: Path, root: Path, script: str, extra: dict[str, str] | None = None
) -> dict[str, str]:
    tree(root, script.replace("NEW", repr(NEW_SOURCE)))
    (root / "src/app/client.py").write_text(CLIENT)
    (root / "src/app/service.py").write_text(SERVICE)
    for name, text in (extra or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    for step in (
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
    ):
        subprocess.run(["git", "-C", str(root), *step], check=True, capture_output=True)
    return statuses(verdict(release_core, root))


def test_a_read_only_script_still_holds_the_symbol_records(
    release_core: Path, tmp_path: Path
) -> None:
    """A read-only script with a `try` is outside the closed grammar: the hold stays.

    The grammar proves a script harmless; no detector of bad forms may do it (AD-1211).
    """
    found = check(release_core, tmp_path, READS)
    assert found["INTERFACE"] == "UNKNOWN", found
    assert run(tmp_path, READS) == "orig"


@pytest.mark.parametrize("name", sorted(WRITES))
def test_a_script_that_writes_a_binding_keeps_the_hold(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    found = check(release_core, tmp_path, WRITES[name])
    assert found["INTERFACE"] == "UNKNOWN", found
    assert run(tmp_path, WRITES[name]) == "hooked", "the plant must change the scanned code"


@pytest.mark.parametrize("name", sorted(HELD))
def test_a_use_that_can_hand_out_a_module_keeps_the_hold(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    assert check(release_core, tmp_path, HELD[name])["INTERFACE"] == "UNKNOWN"


# Each script is in the closed grammar: `import` of `sys` and `importlib.*`, a read of a text, a
# test of `sys.modules`, `find_spec` of a top-level name against `None`, `print` of a read. No path
# is written, nothing is defined and no package is imported.
CLOSED = {
    "reads": (
        "import importlib.metadata\nimport importlib.util\nimport sys\n\n"
        'assert importlib.util.find_spec("zzz_never_installed") is None\n'
        'assert "zzz_never_installed" not in sys.modules\n'
        'print("app" in sys.modules, importlib.metadata.version("pip"))\n'
        'if "app" in sys.modules or not "app" in sys.modules:\n    print("done")\n'
    ),
    "plain f-string is the text": (
        'import sys\n\nprint(f"app", f"app" in sys.modules)\nname = "x"\nprint(name)\n'
    ),
    "from import": (
        "from importlib.util import find_spec\nfrom importlib.metadata import version\n"
        'print(find_spec("zzz_never_installed") is None, version("pip"))\n'
    ),
}


@pytest.mark.parametrize("name", sorted(CLOSED))
def test_a_script_in_the_closed_grammar_holds_nothing(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    found = check(release_core, tmp_path, CLOSED[name])
    assert found == dict.fromkeys(found, "PASS"), found
    assert "hooked" not in run(tmp_path, CLOSED[name])


# One form outside the grammar keeps the hold of the whole file, with a read next to it.
OUTSIDE = {
    "a def": CLOSED["reads"] + "\n\ndef unused():\n    return 1\n",
    "a try": (
        "import importlib.metadata\n\ntry:\n    importlib.metadata.version('app')\n"
        "except importlib.metadata.PackageNotFoundError:\n    pass\n"
    ),
    "an alias": CLOSED["reads"].replace("import sys", "import sys as system"),
    "a call of another function": CLOSED["reads"] + 'print(len("x"))\n',
    "a keyword of print": CLOSED["reads"] + 'print("x", end="")\n',
    "a name used twice": CLOSED["reads"] + 'name = "a"\nname = "b"\n',
    "a name passed on": CLOSED["reads"] + 'name = "a"\nprint(len(name))\n',
    "a test of an object": CLOSED["reads"] + 'name = "a"\nassert name in sys.modules\n',
    "files of a package of the scan": CLOSED["reads"]
    + 'import importlib.resources\nprint(importlib.resources.files("app"))\n',
    "find_spec of a submodule": CLOSED["reads"]
    + 'assert importlib.util.find_spec("app.service") is None\n',
}


@pytest.mark.parametrize("name", sorted(OUTSIDE))
def test_one_form_outside_the_grammar_keeps_the_hold(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    assert check(release_core, tmp_path, OUTSIDE[name])["INTERFACE"] == "UNKNOWN"


# A loader or resource API with a name that is not a text written in the source: the name can be
# any module of the scan, so the file holds each of them (no hook is needed to see the hold).
COMPUTED = {
    "import_module": "import importlib\nname = 'ap' + 'p'\nimportlib.import_module(name)\n",
    "__import__": "name = ''.join(['ap', 'p'])\n__import__(name)\n",
    "find_spec": "import importlib.util\nname = 'ap' + 'p'\nimportlib.util.find_spec(name)\n",
    "version": "import importlib.metadata\nimportlib.metadata.version('a' + 'pp')\n",
    "distribution": "from importlib.metadata import distribution\ndistribution(f'a{1}')\n",
    "exec": "exec('a' + 'pp')\n",
    "runpy": "import runpy\nrunpy.run_module('a' + 'pp')\n",
    "spec_from_file_location": (
        "import importlib.util\nimportlib.util.spec_from_file_location('a' + 'pp', 'x.py')\n"
    ),
    "files with an alias": (
        "import importlib.resources as resources\nresources.files('a' + 'pp')\n"
    ),
}


@pytest.mark.parametrize("name", sorted(COMPUTED))
def test_a_computed_name_in_a_loader_call_holds_every_module(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    assert check(release_core, tmp_path, COMPUTED[name])["INTERFACE"] == "UNKNOWN"


# `files(text)` imports the package of the text: the initializer of a package outside the scan runs
# code that no site shows (Codex #2144). Only a module of the scan is proven.
PAYLOAD = {
    "scripts/payload/__init__.py": (
        "import pathlib\n"
        'pathlib.Path("src/app/service.py").write_text("def f():\\n    return \'hooked\'\\n")\n'
    ),
    "scripts/payload/sub.py": "",
}
RUNS_PACKAGE_CODE = {
    "files of an outside package": (
        "from importlib.resources import files\n"
        'print(files("payload").joinpath("app.service").read_text())\n'
    ),
    "find_spec of a submodule": (
        'import importlib.util\nassert importlib.util.find_spec("payload.sub") is None\n'
        'print("app.service")\n'
    ),
}

# A package beside the script shadows the package of the scan: `files("app")` runs its initializer.
SHADOW = {"scripts/app/__init__.py": PAYLOAD["scripts/payload/__init__.py"]}
SHADOWED = (
    "from importlib.resources import files\n"
    'print(files("app").joinpath("app.service").read_text())\n'
)


def test_files_of_a_name_that_a_package_beside_the_script_shadows_keeps_the_hold(
    release_core: Path, tmp_path: Path
) -> None:
    assert check(release_core, tmp_path, SHADOWED, SHADOW)["INTERFACE"] == "UNKNOWN"
    run(tmp_path, SHADOWED)
    assert "hooked" in (tmp_path / "src/app/service.py").read_text()


@pytest.mark.parametrize("name", sorted(RUNS_PACKAGE_CODE))
def test_a_resource_read_of_a_package_outside_the_scan_keeps_the_hold(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    script = RUNS_PACKAGE_CODE[name]
    assert check(release_core, tmp_path, script, PAYLOAD)["INTERFACE"] == "UNKNOWN"
    assert run(tmp_path, script) != "orig"
    assert "hooked" in (tmp_path / "src/app/service.py").read_text()


def test_find_spec_of_a_top_level_name_imports_nothing(release_core: Path, tmp_path: Path) -> None:
    script = 'import importlib.util\nassert importlib.util.find_spec("payload") is not None\n'
    assert check(release_core, tmp_path, script, PAYLOAD)["INTERFACE"] == "PASS"
    run(tmp_path, script)
    assert "hooked" not in (tmp_path / "src/app/service.py").read_text()

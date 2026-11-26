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

PREMISE = {
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
}

NEW_SOURCE = "def f():\n    return 'hooked'\n"

WRITES = {
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


def check(release_core: Path, root: Path, script: str) -> dict[str, str]:
    tree(root, script.replace("NEW", repr(NEW_SOURCE)))
    (root / "src/app/client.py").write_text(CLIENT)
    (root / "src/app/service.py").write_text(SERVICE)
    for step in (
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
    ):
        subprocess.run(["git", "-C", str(root), *step], check=True, capture_output=True)
    return statuses(verdict(release_core, root))


def test_a_read_only_script_still_holds_the_symbol_records(
    release_core: Path, tmp_path: Path
) -> None:
    """The hold is restored (revert of #2072): no outside script is proven read-only today.

    A script that only reads (`version`, `files(...).read_text()`, `in sys.modules`) is harmless,
    but a detector of bad forms in a script assumed harmless leaked five times. A closed grammar
    of allowed forms has to prove it first.
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


@pytest.mark.xfail(
    strict=True,
    reason="a name that the file does not spell as a plain string is the stated premise (AD-770): "
    "known limit, docs/known-limits.md",
)
@pytest.mark.parametrize("name", sorted(PREMISE))
def test_a_computed_name_is_a_known_limit_not_a_hold(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    found = check(release_core, tmp_path, PREMISE[name])
    assert run(tmp_path, PREMISE[name]) == "hooked", "the plant must change the scanned code"
    assert found["INTERFACE"] == "UNKNOWN", found

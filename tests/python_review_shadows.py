# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shadow and control plants of the delta review of #1178 at `05a34180b` (AD-504, #880).

Each plant is a Python tree for the rule `interface_boundary`: a package `app.lib` with a public
entry, a consumer module, and the files that write to the package or bind its names. `truth` is
what real Python binds when the consumer is imported (measured by the reviewer): FAIL means the
public thing is not what the consumer gets. The core must never give PASS for such a plant, except
for the plants that the documents name as open false PASS (`OPEN`). A plant of truth PASS must
never give FAIL. The plants fail against `05a34180b`: 34 of them gave PASS there.
"""

from __future__ import annotations

PLANTS: dict[str, dict[str, object]] = {
    "a-comprehension-target": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\n"
            "from app.lib._priv import secret\n"
            "_l = [0 for f in [secret]]\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "PASS",
    },
    "a-conditional-import": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "try:\n"
            "    from app.lib.pub import f\n"
            "except ImportError:\n"
            "    from app.lib._priv import f\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "PASS",
    },
    "a-control-clean": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "PASS",
    },
    "a-from-dot-submodule": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nfrom . import f\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "f.py": "x = 1\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "PASS",
    },
    "a-from-dot-submodule-as-other": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nfrom . import f as _m\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "f.py": "x = 1\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "PASS",
    },
    "a-method-default-walrus": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\n"
            "from app.lib._priv import secret\n"
            "class _C:\n"
            "    def m(self, x=(f := secret)): pass\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "PASS",
    },
    "a-star-before": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib._priv import *\nfrom app.lib.pub import f\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "PASS",
    },
    "d-S1-tc-chain": {
        "consumer": "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "PASS",
    },
    "s-class-base-walrus": {
        "consumer": "from app.lib import run\n",
        "files": {
            "__init__.py": "class _C((run := object)): pass\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
            "run.py": "x = 1\n",
        },
        "public": ["app.lib.run"],
        "truth": "FAIL",
    },
    "s-control-plain": {
        "consumer": "from app.lib import run\n",
        "files": {
            "__init__.py": "",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
            "run.py": "x = 1\n",
        },
        "public": ["app.lib.run"],
        "truth": "PASS",
    },
    "s-decorator-walrus": {
        "consumer": "from app.lib import run\n",
        "files": {
            "__init__.py": "@((run := 1) and (lambda fn: fn))\ndef _g(): pass\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
            "run.py": "x = 1\n",
        },
        "public": ["app.lib.run"],
        "truth": "FAIL",
    },
    "s-default-walrus": {
        "consumer": "from app.lib import run\n",
        "files": {
            "__init__.py": "def _g(x=(run := 1)): pass\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
            "run.py": "x = 1\n",
        },
        "public": ["app.lib.run"],
        "truth": "FAIL",
    },
    "x-shadow-assigned-getattr": {
        "consumer": "from app.lib import run\n",
        "files": {
            "__init__.py": "__getattr__ = lambda name: 1\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
            "run.py": "x = 1\n",
        },
        "public": ["app.lib.run"],
        "truth": "FAIL",
    },
    "x-shadow-imported-getattr": {
        "consumer": "from app.lib import run\n",
        "files": {
            "__init__.py": "from app.lib._hook import __getattr__\n",
            "_hook.py": "def __getattr__(name):\n    return 1\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
            "run.py": "x = 1\n",
        },
        "public": ["app.lib.run"],
        "truth": "FAIL",
    },
    "x-shadow-nested-getattr": {
        "consumer": "from app.lib import run\n",
        "files": {
            "__init__.py": "if True:\n    def __getattr__(name):\n        return 1\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
            "run.py": "x = 1\n",
        },
        "public": ["app.lib.run"],
        "truth": "FAIL",
    },
    "x-shadow-other-alias": {
        "consumer": "from app.lib import run\n",
        "files": {
            "__init__.py": "import app.lib._patch\n",
            "_patch.py": "from app import lib\nm = lib\nm.run = 1\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
            "run.py": "x = 1\n",
        },
        "public": ["app.lib.run"],
        "truth": "FAIL",
    },
    "x-shadow-other-setattr": {
        "consumer": "from app.lib import run\n",
        "files": {
            "__init__.py": "import app.lib._patch\n",
            "_patch.py": "from app import lib\nsetattr(lib, 'run', 1)\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
            "run.py": "x = 1\n",
        },
        "public": ["app.lib.run"],
        "truth": "FAIL",
    },
    "x-shadow-other-write": {
        "consumer": "from app.lib import run\n",
        "files": {
            "__init__.py": "import app.lib._patch\n",
            "_patch.py": "from app import lib\nlib.run = 1\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
            "run.py": "x = 1\n",
        },
        "public": ["app.lib.run"],
        "truth": "FAIL",
    },
}

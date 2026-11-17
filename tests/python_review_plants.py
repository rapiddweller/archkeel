# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The write plants of the delta review of #1178 at `05a34180b` (AD-504, #880).

Each plant is a Python tree for the rule `interface_boundary`: a package `app.lib` with a public
entry, a consumer module, and the files that write to the package or bind its names. `truth` is
what real Python binds when the consumer is imported (measured by the reviewer): FAIL means the
public thing is not what the consumer gets. The core must never give PASS for such a plant, except
for the plants that the documents name as open false PASS (`OPEN`). A plant of truth PASS must
never give FAIL. The plants fail against `05a34180b`: 34 of them gave PASS there.
"""

from __future__ import annotations

PLANTS: dict[str, dict[str, object]] = {
    "b-alias-chain": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "M = lib\n"
            "M.f = secret\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-alias-import-as": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "import app.lib as L\n"
            "from app.lib._priv import secret\n"
            "M = L\n"
            "M.f = secret\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-all-alias": {
        "consumer": "from app.lib import g\n",
        "files": {
            "__init__.py": "def f(): pass\n"
            "def g(): pass\n"
            "__all__ = ['f', 'g']\n"
            "import app.lib._patch\n",
            "_patch.py": "from app import lib\nnames = lib.__all__\nnames.remove('g')\n",
        },
        "public": ["app.lib"],
        "truth": "FAIL",
    },
    "b-all-getattr": {
        "consumer": "from app.lib import g\n",
        "files": {
            "__init__.py": "def f(): pass\n"
            "def g(): pass\n"
            "__all__ = ['f', 'g']\n"
            "import app.lib._patch\n",
            "_patch.py": "from app import lib\ngetattr(lib, '__all__').remove('g')\n",
        },
        "public": ["app.lib"],
        "truth": "FAIL",
    },
    "b-all-imported": {
        "consumer": "from app.lib import g\n",
        "files": {
            "__init__.py": "def f(): pass\n"
            "def g(): pass\n"
            "__all__ = ['f', 'g']\n"
            "import app.lib._patch\n",
            "_patch.py": "from app.lib import __all__ as names\nnames.remove('g')\n",
        },
        "public": ["app.lib"],
        "truth": "FAIL",
    },
    "b-all-list-remove": {
        "consumer": "from app.lib import g\n",
        "files": {
            "__init__.py": "def f(): pass\n"
            "def g(): pass\n"
            "__all__ = ['f', 'g']\n"
            "import app.lib._patch\n",
            "_patch.py": "from app import lib\nlist.remove(lib.__all__, 'g')\n",
        },
        "public": ["app.lib"],
        "truth": "FAIL",
    },
    "b-all-param": {
        "consumer": "from app.lib import g\n",
        "files": {
            "__init__.py": "def f(): pass\n"
            "def g(): pass\n"
            "__all__ = ['f', 'g']\n"
            "import app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "def drop(names):\n"
            "    names.remove('g')\n"
            "drop(lib.__all__)\n",
        },
        "public": ["app.lib"],
        "truth": "FAIL",
    },
    "b-comprehension-target": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "_l = [0 for lib.f in [secret]]\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-conditional-expr": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "(lib if True else lib).f = secret\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-dict-alias": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "d = lib.__dict__\n"
            "d['f'] = secret\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-dict-imported": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app.lib import __dict__ as d\n"
            "from app.lib._priv import secret\n"
            "d['f'] = secret\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-dunder-setattr": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "lib.__setattr__('f', secret)\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-getattr-pkg": {
        "consumer": "from app.lib.pub import install\ninstall()\nfrom app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\n"
            "def g(): pass\n"
            "def install():\n"
            "    import app\n"
            "    from app.lib._priv import secret\n"
            "    getattr(app, 'lib').f = secret\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-holder-attr": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "class H:\n"
            "    m = lib\n"
            "H.m.f = secret\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-list-item": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "[lib][0].f = secret\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-monkeypatch-style": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "class MonkeyPatch:\n"
            "    def setattr(self, target, name, value):\n"
            "        setattr(target, name, value)\n"
            "MonkeyPatch().setattr(lib, 'f', secret)\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-object-setattr": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "object.__setattr__(lib, 'f', secret)\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-outside-roots-conftest": {
        "consumer": "from app.lib import f\n",
        "files": {
            "ROOT/conftest.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "lib.f = secret\n",
            "__init__.py": "from app.lib.pub import f\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-outside-roots-sitecustomize": {
        "consumer": "from app.lib import f\n",
        "files": {
            "ROOT/tools/boot.py": "from app import lib\n"
            "from app.lib._priv import "
            "secret\n"
            "lib.f = secret\n",
            "__init__.py": "from app.lib.pub import f\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-param": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "def patch(m):\n"
            "    m.f = secret\n"
            "patch(lib)\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-setattr-alias": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "put = setattr\n"
            "put(lib, 'f', secret)\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-setattr-partial": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "import functools\n"
            "functools.partial(setattr, lib)('f', secret)\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "b-submodule-later-relative": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from . import f as _m\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "f.py": "x = 1\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "PASS",
    },
    "b-vars-alias": {
        "consumer": "from app.lib import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app import lib\n"
            "from app.lib._priv import secret\n"
            "d = vars(lib)\n"
            "d['f'] = secret\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
    "d-S4-attr-through-module": {
        "consumer": "import app.lib\napp.lib._priv.secret()\n",
        "files": {
            "__init__.py": "from app.lib import _priv\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib"],
        "truth": "FAIL",
    },
    "x-target-module-write": {
        "consumer": "from app.lib.pub import f\n",
        "files": {
            "__init__.py": "from app.lib.pub import f\nimport app.lib._patch\n",
            "_patch.py": "from app.lib import pub\n"
            "from app.lib._priv import secret\n"
            "p = pub\n"
            "p.f = secret\n",
            "_priv.py": "def secret(): pass\ndef f(): pass\ndef run(): pass\n",
            "pub.py": "def f(): pass\ndef g(): pass\n",
        },
        "public": ["app.lib.pub"],
        "truth": "FAIL",
    },
}

# The forms that the core still passes where the truth is FAIL, named in AD-504 and
# `docs/known-limits.md` and pinned here: a fix removes the name from this set. AD-708 removed
# `d-S4-attr-through-module` (#1415).
OPEN = frozenset(
    {
        "b-outside-roots-conftest",
        "b-outside-roots-sitecustomize",
    }
)

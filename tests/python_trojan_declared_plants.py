# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
# ruff: noqa
"""Declared-import plants of the second counter-example run of #1968 (AD-1058)."""

from test_cli_python_trojan_horse_name import (
    BLOB,
    MODEL,
    PAGE,
    pickle_declaration,
)

OTHER = "src/app/service/other.py"
IM = "import app.service.model as model\n"
cases = {
    "X0 control attribute": (
        {MODEL: "import pickle\n", PAGE: IM + f"model.pickle.loads({BLOB})\n"},
        [pickle_declaration()],
    ),
    "X1 from operator import attrgetter as ag": (
        {
            MODEL: "import pickle\n",
            PAGE: IM
            + f"from operator import attrgetter as ag\nag('pickle')(model).loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X2 from inspect import getmembers as gm": (
        {
            MODEL: "import pickle\n",
            PAGE: IM
            + f"from inspect import getmembers as gm\ndict(gm(model))['pickle'].loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X3 inspect.getattr_static(model,'pickle')": (
        {
            MODEL: "import pickle\n",
            PAGE: IM + f"import inspect\ninspect.getattr_static(model, 'pickle').loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X3b inspect.getattr_static computed": (
        {
            MODEL: "import pickle\n",
            PAGE: IM
            + f"import inspect\ninspect.getattr_static(model, 'pick'+'le').loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X4 sys.modules literal key then .pickle": (
        {
            MODEL: "import pickle\n",
            PAGE: f"import sys\nimport app.service.model\nsys.modules['app.service.model'].pickle.loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X5 from builtins import vars as v": (
        {
            MODEL: "import pickle\n",
            PAGE: IM + f"from builtins import vars as v\nv(model)['pickle'].loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X6 third module star-imports model, page uses other.pickle": (
        {
            MODEL: "import pickle\n",
            OTHER: "from app.service.model import *\n",
            PAGE: f"import app.service.other as o\no.pickle.loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X7 third module: import app.service.model as m; pickle=m.pickle ; page uses": (
        {
            MODEL: "import pickle\n",
            OTHER: "import app.service.model as m\nUSE = m.pickle\n",
            PAGE: f"import app.service.other as o\no.USE.loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X8 getattr via lambda default alias": (
        {
            MODEL: "import pickle\n",
            PAGE: IM + f"g = getattr\ng(model, 'pick'+'le').loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X9 dir(model)+ operator.itemgetter(vars) ": (
        {
            MODEL: "import pickle\n",
            PAGE: IM
            + f"import operator\noperator.itemgetter('pickle')(model.__dict__).loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X10 model.__getattr__ stored alias m2": (
        {
            MODEL: "import pickle\ndef __getattr__(n):\n    return pickle\n",
            PAGE: IM + f"model.__getattr__('x').loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X11 class attr copy: class K: p = model.pickle": (
        {
            MODEL: "import pickle\n",
            PAGE: IM + f"class K:\n    p = model.pickle\nK.p.loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X12 copy.copy(model).pickle": (
        {
            MODEL: "import pickle\n",
            PAGE: IM + f"import copy\ncopy.copy(model).pickle.loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X13 type annotation use / functools.partial(model.pickle.loads)": (
        {
            MODEL: "import pickle\n",
            PAGE: IM + f"import functools\nfunctools.partial(model.pickle.loads)({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X14 importer is the model's sibling; page does `import app.service.model` and uses `app.service.model.pickle` via from app import service": (
        {
            MODEL: "import pickle\n",
            PAGE: f"from app import service\nimport app.service.model\nservice.model.pickle.loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X15 page reads model attribute in a function default arg": (
        {
            MODEL: "import pickle\n",
            PAGE: IM + f"def run(p=model.pickle):\n    p.loads({BLOB})\nrun()\n",
        },
        [pickle_declaration()],
    ),
    "X16 page: model passed to other.helper(model) which getattr()": (
        {
            MODEL: "import pickle\n",
            OTHER: "def helper(m, n):\n    return getattr(m, n)\n",
            PAGE: IM
            + f"import app.service.other as o\no.helper(model, 'pick'+'le').loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
    "X17 helper in other module (non-importer of model) gets model from page by param, uses getattr(m,'pickle') literal": (
        {
            MODEL: "import pickle\n",
            OTHER: "def helper(m):\n    return getattr(m, 'pickle')\n",
            PAGE: IM + f"import app.service.other as o\no.helper(model).loads({BLOB})\n",
        },
        [pickle_declaration()],
    ),
}

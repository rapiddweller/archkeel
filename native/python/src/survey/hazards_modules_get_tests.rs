// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! #2197: a `sys.modules.get("text")` that is only compared by identity is no import-system
//! change. Each other use keeps the site, also a truth test (Codex #2200: it runs `__bool__`).

use super::clear_count;

const SITE: &str = "sys.modules";

#[test]
fn a_lookup_that_is_only_compared_or_tested_is_no_site() {
    for source in [
        // The issue.
        "import sys\n\ndef is_math(value):\n    found = sys.modules.get(\"math\")\n    return found is not None and value is found\n",
        "import sys\n\ndef f(value):\n    return sys.modules.get(\"math\") is value\n",
        "import sys\n\ndef f():\n    return sys.modules.get(\"x\") is None\n",
        "import sys\nok = sys.modules.get(\"x\") is not None\n",
        "import sys as s\nok = s.modules.get(\"x\") is None\n",
    ] {
        assert_eq!(clear_count(source, SITE), 0, "{source}");
    }
}

#[test]
fn each_other_use_of_a_lookup_keeps_the_site() {
    for source in [
        "import sys\nif sys.modules.get(\"x\"):\n    pass\n",
        "import sys\nif not sys.modules.get(\"x\") and a:\n    pass\n",
        "import sys\nwhile sys.modules.get(\"x\"):\n    break\n",
        "import sys\nassert sys.modules.get(\"x\")\n",
        "import sys\nv = 1 if sys.modules.get(\"x\") else 2\n",
        "import sys\n\ndef f():\n    m = sys.modules.get(\"x\")\n    if m:\n        return 1\n    return m is None\n",
        "import sys\n\ndef f():\n    return sys.modules.get(\"x\")\n",
        "import sys\n\ndef f():\n    m = sys.modules.get(\"x\")\n    return m\n",
        "import sys\n\ndef f():\n    m = sys.modules.get(\"x\")\n    return m.attr\n",
        "import sys\n\ndef f():\n    return sys.modules.get(\"x\").attr\n",
        "import sys\n\ndef f():\n    return sys.modules.get(\"x\") == other\n",
        "import sys\n\ndef f():\n    m = sys.modules.get(\"x\")\n    return m == other\n",
        "import sys\n\ndef f(n):\n    return sys.modules.get(n) is None\n",
        "import sys\n\ndef f():\n    return sys.modules.get(\"x\", None) is None\n",
        "import sys\n\ndef f():\n    m = sys.modules.get(\"x\")\n    g(m)\n    return m is None\n",
        "import sys\n\ndef f():\n    m = sys.modules.get(\"x\")\n    m()\n",
        "import sys\n\ndef f():\n    m = sys.modules.get(\"x\")\n    return m is None or m\n",
        "import sys\n\ndef f():\n    m = sys.modules.get(\"x\")\n    other = m\n    return m is None\n",
        "import sys\n\ndef f():\n    m = sys.modules.get(\"x\")\n    return m is None\n\ndef g():\n    m = 1\n",
        "import sys\n\ndef f():\n    global m\n    m = sys.modules.get(\"x\")\n    return m is None\n",
        "import sys\nm = sys.modules.get(\"x\")\nok = m is None\n",
        "import sys\nv = sys.modules.get(\"x\") or 1\n",
        "import sys\nv = [sys.modules.get(\"x\")]\n",
        "import sys\nsys.modules[\"x\"] = o\nok = sys.modules.get(\"y\") is None\n",
        "import sys\ndel sys.modules[\"x\"]\n",
        "import sys\nsys.modules.setdefault(\"x\", o)\n",
        "import sys\nsys.modules.pop(\"x\")\n",
        "import sys\nsys.modules.update(o)\n",
        "import sys\nsys = other\nok = sys.modules.get(\"x\") is None\n",
        "from sys import modules\nok = modules.get(\"x\") is None\n",
        "ok = sys.modules.get(\"x\") is None\n",
        "import sys\nok = sys.modules.get(\"x\") in other\n",
        "import sys\nok = sys.modules.get(\"x\") is None == other\n",
    ] {
        assert!(clear_count(source, SITE) >= 1, "{source}");
    }
}

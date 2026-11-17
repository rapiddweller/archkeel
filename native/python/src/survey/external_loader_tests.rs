// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a forbidden dependency through a loader outside the scan is never PASS (#1519).

use crate::survey::targets::tests::surveyed;

fn gaps(user: &str) -> Vec<String> {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/lib/__init__.py", "value = 1\n"),
        ("src/app/user.py", user),
    ]);
    let mut reasons: Vec<String> = (found.unknowns.iter())
        .map(|gap| gap.title.clone())
        .filter(|title| title.starts_with("external_loader"))
        .collect();
    reasons.sort();
    reasons
}

#[test]
fn a_call_of_an_outside_value_with_the_name_of_a_module_is_a_gap() {
    for user in [
        "from plugin import load\nload('app.lib')\n",
        "import plugin\nplugin.loader.load(name='app.lib:value')\n",
        "from plugin import namespace\nnamespace()['x']('app.lib')\n",
        "def f():\n    import plugin as p\n    p.load('app.lib.value')\n",
    ] {
        assert_eq!(gaps(user), ["external_loader: app.lib"], "{user}");
    }
}

#[test]
fn a_known_callee_or_a_string_above_the_module_is_no_gap() {
    for user in [
        // The standard library, the scan itself and a builtin are read or known.
        "import os\nos.getenv('app.lib')\n",
        "from app import lib\nlib.value('app.lib')\n",
        "print('app.lib')\n",
        // The package above the module of the call: Python imports it already.
        "from plugin import get_logger\nget_logger('app')\n",
        "from plugin import emit\nemit('app.user.done')\n",
        // No module of the scan, or no dotted name.
        "from plugin import load\nload('other.lib')\nload('app lib')\n",
    ] {
        assert_eq!(gaps(user), Vec::<String>::new(), "{user}");
    }
}

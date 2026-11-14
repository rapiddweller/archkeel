// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: an import under the guard leaves a rule with `include_type_checking: false`. A
// look-alike guard would hide a runtime edge, so each one must be no guard.

use super::*;

/// Whether the test of the first `if` statement of the module is the guard.
fn guarded(source: &str) -> bool {
    let tree = crate::test_tree(source, 14).expect("valid probe");
    let guard = Guard::of(&tree, &Binders::of(&tree));
    let test = tree.body.iter().find_map(|stmt| match stmt {
        Stmt::If(node) => Some(&*node.test),
        _ => None,
    });
    guard.holds(test.expect("an if statement"))
}

#[test]
fn a_type_checking_name_bound_only_by_typing_is_the_guard() {
    for source in [
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    pass\n",
        "from typing_extensions import TYPE_CHECKING\nif TYPE_CHECKING:\n    pass\n",
        "from typing import TYPE_CHECKING as TC\nif TC:\n    pass\n",
        "import typing\nif typing.TYPE_CHECKING:\n    pass\n",
        "import typing as t\nif t.TYPE_CHECKING:\n    pass\n",
    ] {
        assert!(guarded(source), "{source}");
    }
}

#[test]
fn a_look_alike_or_rebound_guard_is_a_runtime_test() {
    for source in [
        "TYPE_CHECKING = False\nif TYPE_CHECKING:\n    pass\n",
        "from config import TYPE_CHECKING\nif TYPE_CHECKING:\n    pass\n",
        "if TYPE_CHECKING:\n    pass\n",
        "import settings\nif settings.TYPE_CHECKING:\n    pass\n",
        "from typing import TYPE_CHECKING\nTYPE_CHECKING = True\nif TYPE_CHECKING:\n    pass\n",
        "from typing import TYPE_CHECKING\ndef f(TYPE_CHECKING):\n    pass\nif TYPE_CHECKING:\n    pass\n",
        "import typing\ntyping = other\nif typing.TYPE_CHECKING:\n    pass\n",
        "from typing import TYPE_CHECKING\nfrom tools import *\nif TYPE_CHECKING:\n    pass\n",
        "from typing import TYPE_CHECKING\nif not TYPE_CHECKING:\n    pass\n",
    ] {
        assert!(!guarded(source), "{source}");
    }
}

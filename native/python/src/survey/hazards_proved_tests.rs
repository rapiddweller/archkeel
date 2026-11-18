// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: a plain statement that is no import gives no gap (AD-894). Each false site has a
// case, and each true site that looks like it keeps its gap.

use super::*;
use crate::survey::targets::tests::{reasons, surveyed};

/// The gap kinds that the survey keeps for one module.
fn kinds_of(source: &str) -> Vec<&'static str> {
    let tree = crate::test_tree(source, 14).expect("valid probe");
    let binders = vec![Binders::of(&tree)];
    let modules = [Module::new(
        "app/x.py".to_owned(),
        "app.x".to_owned(),
        source.to_owned(),
        tree,
    )];
    let (_, found) = split(&modules, &binders, None);
    found.iter().map(|(_, site)| site.kind).collect()
}

fn has(source: &str, kind: &str) -> bool {
    kinds_of(source).contains(&kind)
}

#[test]
fn a_call_of_a_function_or_class_of_the_module_with_a_door_module_name_is_no_gap() {
    for source in [
        "def inspect(x):\n    return x\ninspect(1)\n",
        "def inspect(x):\n    return x\ndef use():\n    return inspect(1)\n",
        "class inspect:\n    pass\ninspect()\n",
        "def code(x):\n    return x\ncode(1)\n",
    ] {
        assert!(kinds_of(source).is_empty(), "{source}");
    }
}

#[test]
fn a_door_module_name_that_is_not_one_plain_definition_keeps_its_gap() {
    for source in [
        "inspect(1)\n",
        "import inspect\ndef f():\n    return inspect.getmodule(x)\n",
        "from x import *\ndef inspect(x):\n    return x\ninspect(1)\n",
        "def inspect(x):\n    return x\ndef inspect(x):\n    return x\ninspect(1)\n",
        "import inspect\ndef inspect(x):\n    return x\ninspect(1)\n",
        "import importlib\nimportlib.import_module(x)\n",
        "def eval(x):\n    return x\neval(1)\n",
    ] {
        assert!(has_dynamic(source), "{source}");
    }
    // The standard `inspect` module keeps its behaviour: only `getmodule` is a door.
    assert!(!has_dynamic("import inspect\ninspect.getmembers(x)\n"));
}

fn has_dynamic(source: &str) -> bool {
    has(source, DYNAMIC)
}

#[test]
fn an_attribute_code_of_a_class_of_the_scan_is_no_gap_and_of_a_module_is() {
    let files = [
        ("src/app/__init__.py", ""),
        (
            "src/app/models.py",
            "class Plan:\n    code = 'x'\n    name = 'n'\n",
        ),
        (
            "src/app/same.py",
            "class Own:\n    code = 1\nvalue = Own.code\n",
        ),
    ];
    let with = |client: &str| {
        let mut all = files.to_vec();
        all.push(("src/app/client.py", client));
        reasons(&surveyed(&all))
    };
    let plain = "from app.models import Plan\ndef use():\n    return Plan.code, Plan.name\n";
    assert!(with(plain).is_empty(), "{:?}", with(plain));
    let aliased = "from app.models import Plan as P\nvalue = P.code\n";
    assert!(with(aliased).is_empty(), "{:?}", with(aliased));
    for source in [
        "import code\ncode.interact()\n",
        "import code as c\nvalue = c.code\n",
        "from app import code\nvalue = code.code\n",
        "from json import Plan\nvalue = Plan.code\n",
        "from app.models import Plan\nPlan = other\nvalue = Plan.code\n",
        "from app.models import Plan\nimport code as Plan\nvalue = Plan.code\n",
    ] {
        assert!(!with(source).is_empty(), "{source}");
    }
}

#[test]
fn a_class_of_the_scan_that_a_package_re_exports_keeps_its_gap() {
    let found = surveyed(&[
        ("src/app/__init__.py", "from app.models import Plan\n"),
        ("src/app/models.py", "class Plan:\n    code = 'x'\n"),
        (
            "src/app/client.py",
            "from app import Plan\nvalue = Plan.code\n",
        ),
    ]);
    assert!(!reasons(&found).is_empty());
}

#[test]
fn a_read_of_sys_path_is_no_import_system_change() {
    for source in [
        "import sys\nx = [p for p in sys.path if p]\n",
        "import sys\nx = {p: 1 for p in sys.path}\n",
        "import sys\nx = [a for b in c for a in sys.path]\n",
        "import sys\nfor p in sys.path:\n    print(p)\n",
        "import sys as s\nx = 'a' in s.path\n",
        "import sys\nx = sys.path[0]\n",
        "import sys\nx = sys.path[:1]\n",
        "import sys\ndef f():\n    return [p for p in sys.path]\n",
    ] {
        assert!(!has(source, IMPORT_SYSTEM), "{source}");
    }
}

#[test]
fn each_change_of_sys_path_is_an_import_system_change() {
    for source in [
        "import sys\nsys.path.append(x)\n",
        "import sys\nsys.path.insert(0, x)\n",
        "import sys\nsys.path.extend(x)\n",
        "import sys\nsys.path.remove(x)\n",
        "import sys\nsys.path.clear()\n",
        "import sys\nsys.path.pop()\n",
        "import sys\nsys.path = [x]\n",
        "import sys\nsys.path += [x]\n",
        "import sys\nsys.path[0] = x\n",
        "import sys\nsys.path[0:0] = x\n",
        "import sys\ndel sys.path[0]\n",
        "import sys\np = sys.path\np.append(x)\n",
        "import sys\nf(sys.path)\n",
        "import sys\nx = [p for p in sys.path.copy()]\n",
        "import sys\nfor sys.path in values:\n    pass\n",
        "from sys import path\npath.append(x)\n",
    ] {
        assert!(has(source, IMPORT_SYSTEM), "{source}");
    }
}

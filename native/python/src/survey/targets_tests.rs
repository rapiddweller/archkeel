// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the store and the model read each target and each site gap (AD-450). A wrong target
// or a missing gap can hide an edge, so each class and each gap condition has a case.

use archkeel_facts::envelope::Target;
use archkeel_snapshot::test_tree::Tree;
use archkeel_wire::request::decode_python;
use serde_json::json;

use super::*;
use crate::survey::Survey;

/// The survey of a tree with the roots `roots` and the namespace `app`.
pub(crate) fn surveyed_in(files: &[(&str, &str)], roots: &[&str], namespace: &str) -> Survey {
    survey_of(&Tree::new(files), roots, namespace, false)
}

/// The survey of an existing tree with the roots `src` and the namespace `app`.
pub(crate) fn surveyed_at(tree: &Tree) -> Survey {
    survey_of(tree, &["src"], "app", false)
}

pub(crate) fn survey_of(tree: &Tree, roots: &[&str], namespace: &str, navigation: bool) -> Survey {
    let raw = json!({
        "protocol_version": "10.0.0",
        "snapshot": {"root": tree.path(), "git_head": "a".repeat(40), "dirty": false},
        "scope": {"roots": roots, "namespace": namespace, "exclude_test_sources": false},
        "resolver": {"language": "python", "phase": "imports", "interpreter": {
            "version": "3.14.0", "stdlib_module_names": ["importlib", "json", "os", "sys"],
            "builtin_module_names": []}},
    });
    let request = decode_python(raw.to_string().as_bytes()).unwrap();
    let mut prepared = crate::requirement::Prepared::of(&request).unwrap();
    prepared.navigation = navigation;
    crate::survey::survey(&prepared).unwrap()
}

pub(crate) fn surveyed(files: &[(&str, &str)]) -> Survey {
    surveyed_in(files, &["src"], "app")
}

/// The reason of each gap of a survey, except the trojan horse sites of a computed attribute name
/// (`getattr(module, key)`): a module is no proven receiver (AD-1058), so a lazy `__getattr__`
/// table keeps that site until a contract declares it. `trojan_names` in
/// `hazards_receiver_tests.rs` covers the site itself.
pub(crate) fn reasons(survey: &Survey) -> Vec<String> {
    let all = survey.unknowns.iter().map(reason);
    all.filter(|text| !text.starts_with("dynamic_import: getattr"))
        .collect()
}

pub(crate) fn reason(gap: &Record<GapFact>) -> String {
    match &gap.data {
        GapFact::CollectionGap(data)
        | GapFact::SourceResolutionGap(data)
        | GapFact::DynamicImportLimit(data)
        | GapFact::PrivateAttributeAccessLimit(data)
        | GapFact::ExceptionGap { data, .. } => data.reason.clone().unwrap_or(gap.title.clone()),
    }
}

/// The survey of the sample `src/app/client.py` with `source`, beside `__init__.py` and `service.py`.
fn client(source: &str, init: &str) -> Survey {
    surveyed(&[
        ("src/app/__init__.py", init),
        ("src/app/client.py", source),
        ("src/app/service.py", "VALUE = 1\n"),
    ])
}

fn kinds(survey: &Survey) -> Vec<&'static str> {
    survey
        .targets
        .iter()
        .map(|target| match target {
            Target::Local { .. } => "local",
            Target::Builtin { .. } => "builtin",
            Target::External { .. } => "external",
            Target::Unresolved { .. } => "unresolved",
        })
        .collect()
}

#[test]
fn the_first_part_decides_project_standard_or_external() {
    for (source, kind) in [
        ("import app.service\n", "local"),
        ("from . import service\n", "local"),
        ("import json\n", "builtin"),
        ("import os.path\n", "builtin"),
        ("import requests.adapters\n", "external"),
        ("import distutils\n", "external"),
    ] {
        let found = client(source, "");
        assert_eq!(kinds(&found), [kind], "{source}");
        assert!(found.unknowns.is_empty(), "{source}: {:?}", reasons(&found));
        assert!(found.coverage.full_scope);
    }
    let found = client("import requests.adapters\n", "");
    assert!(
        matches!(&found.targets[0], Target::External { package, .. } if package.as_str() == "requests")
    );
}

#[test]
fn a_project_name_without_a_module_is_unresolved_with_a_gap() {
    let found = client("import app.missing\n", "");
    assert_eq!(kinds(&found), ["unresolved"]);
    assert_eq!(reasons(&found), [format!("{NOT_FOUND}: app.missing")]);
    assert!(!found.coverage.full_scope);
}

#[test]
fn a_relative_import_above_the_top_package_is_a_gap() {
    let found = client("from ... import other\n", "");
    assert_eq!(kinds(&found), ["unresolved"]);
    assert!(
        reasons(&found)[0].starts_with(BEYOND_TOP),
        "{:?}",
        reasons(&found)
    );
}

#[test]
fn a_star_import_of_a_project_module_is_a_gap_and_of_a_package_is_not() {
    let found = client("from app import *\n", "");
    assert_eq!(reasons(&found), [format!("{STAR}: app")]);
    assert!(client("from json import *\n", "").unknowns.is_empty());
}

#[test]
fn a_name_that_can_be_an_attribute_or_a_submodule_is_a_gap() {
    for init in [
        "service = 1\n",
        "def __getattr__(name):\n    return name\n",
        "from json import *\n",
    ] {
        let found = client("from app import service\n", init);
        assert!(
            reasons(&found).contains(&format!("{AMBIGUOUS}: app.service")),
            "{init}: {:?}",
            reasons(&found)
        );
    }
    // The package body imports the submodule: the import system binds it before `__getattr__`.
    let own = "from .service import VALUE\ndef __getattr__(name):\n    return name\n";
    assert!(client("from app import service\n", own).unknowns.is_empty());
    // No binding: the submodule. A binding without a submodule: the attribute.
    assert!(client("from app import service\n", "").unknowns.is_empty());
    assert!(client("from app import other\n", "other = 1\n")
        .unknowns
        .is_empty());
}

#[test]
fn a_package_directory_without_init_is_a_gap_in_each_import_form() {
    for source in [
        "import app.space\n",
        "from app import space\n",
        "from . import space\n",
    ] {
        let found = surveyed(&[
            ("src/app/__init__.py", ""),
            ("src/app/client.py", source),
            ("src/app/space/inner.py", ""),
        ]);
        assert_eq!(
            reasons(&found),
            [format!("{NOT_FOUND}: app.space")],
            "{source}"
        );
    }
    // A name of the package body that no directory has stays an attribute of the package.
    let attribute = surveyed(&[
        ("src/app/__init__.py", "space = 1\n"),
        ("src/app/client.py", "from app import space\n"),
    ]);
    assert!(attribute.unknowns.is_empty(), "{:?}", reasons(&attribute));
}

#[test]
fn a_proven_literal_call_is_a_local_edge_without_a_gap() {
    let found = client(
        "import importlib\nload = lambda: importlib.import_module('app.service')\n",
        "",
    );
    assert!(found.unknowns.is_empty(), "{:?}", reasons(&found));
    assert_eq!(kinds(&found), ["builtin", "local"]);
    let call = found
        .imports
        .iter()
        .find(|r| r.data.data().target_module.as_str() == "app.service");
    let data = call.expect("the call is an import record").data.data();
    assert_eq!(data.binding, None);
    assert!(!data.module_level_import && !data.reexport);
    let init = client(
        "",
        "import importlib\nimportlib.import_module('app.service')\n",
    );
    let call = init
        .imports
        .iter()
        .find(|r| r.data.data().target_module.as_str() == "app.service");
    let data = call
        .expect("the call in the package body is a record")
        .data
        .data();
    assert!(
        !data.reexport,
        "a call in a package body re-exports nothing"
    );
    let computed = client("import importlib\nimportlib.import_module(name)\n", "");
    assert!(
        reasons(&computed)
            .iter()
            .all(|r| r.starts_with("dynamic_import")),
        "{:?}",
        reasons(&computed)
    );
    assert!(!computed.unknowns.is_empty());
}

#[test]
fn a_write_to_the_importlib_loader_withholds_the_literal_edge() {
    for write in [
        "from builtins import setattr as put\nput(importlib, 'import_module', other)",
        "from builtins import delattr as remove\nremove(importlib, 'import_module')",
        "from builtins import setattr as put\napply = put\napply(importlib, 'import_module', other)",
        "import builtins as b\nb.setattr(importlib, 'import_module', other)",
        "importlib.import_module = other",
        "del importlib.import_module",
        "module = importlib\nmodule.import_module = other",
        "importlib.__setattr__('import_module', other)",
        "object.__setattr__(importlib, 'import_module', other)",
        "importlib.__dict__['import_module'] = other",
        "vars(importlib)['import_module'] = other",
    ] {
        let found = client(
            &format!("import importlib\n{write}\nimportlib.import_module('app.service')\n"),
            "",
        );
        assert!(!kinds(&found).contains(&"local"), "{write}");
        assert!(reasons(&found).iter().any(|reason| reason.starts_with("dynamic_import")), "{write}");
    }
}

#[test]
fn a_loader_write_in_another_scanned_module_withholds_the_literal_edge() {
    let found = client(
        "import importlib\nimportlib.import_module('app.service')\n",
        "import importlib as loader\nfrom builtins import setattr as put\nput(loader, 'import_module', other)\n",
    );
    assert!(!kinds(&found).contains(&"local"));
    assert!(reasons(&found)
        .iter()
        .any(|reason| reason.starts_with("dynamic_import")));
}

#[test]
fn a_shadowed_writer_or_receiver_does_not_withhold_the_edge() {
    for source in [
        "import importlib as loader\ndef f(loader):\n    loader.import_module = other\n",
        "import importlib as loader\ndef f():\n    import other as loader\n    loader.import_module = other\n",
        "from builtins import setattr as put\nimport importlib as loader\ndef f(put):\n    put(loader, 'import_module', other)\n",
        "import importlib as loader\nalias = loader\ndef f(alias):\n    alias.import_module = other\n",
        "import importlib as loader\ndef f(loader):\n    alias = loader\n    alias.import_module = other\n",
        "from builtins import setattr as put\nimport importlib as loader\nf = lambda put: put(loader, 'import_module', other)\n",
        "from builtins import setattr as put\nimport importlib as loader\n[put(loader, 'import_module', other) for put in callbacks]\n",
    ] {
        let found = client(
            "import importlib\nimportlib.import_module('app.service')\n",
            source,
        );
        assert!(kinds(&found).contains(&"local"), "{source}");
    }
}

#[test]
fn a_possible_write_in_the_imports_own_scope_still_withholds_the_edge() {
    for source in [
        "import importlib as loader\ndef f():\n    loader.import_module = other\n",
        "def f():\n    import importlib as loader\n    loader.import_module = other\n",
        "import importlib as loader\ndef f(flag):\n    import importlib as local\n    if flag:\n        local = other\n    local.import_module = other\n",
    ] {
        let found = client(
            "import importlib\nimportlib.import_module('app.service')\n",
            source,
        );
        assert!(!kinds(&found).contains(&"local"), "{source}");
        assert!(reasons(&found).iter().any(|reason| reason.starts_with("dynamic_import")), "{source}");
    }
}

#[test]
fn a_replaced_importlib_loader_does_not_withhold_the_builtin_import() {
    let found = client(
        "import importlib\nimportlib.import_module = other\n__import__('app.service')\n",
        "",
    );
    assert!(kinds(&found).contains(&"local"));
}

#[test]
fn unrelated_writes_and_open_trojan_horses_keep_the_literal_edge() {
    for write in [
        "setattr(other, 'import_module', value)",
        "setattr(importlib, 'unrelated', value)",
        "def setattr(obj, name, value):\n    pass\nsetattr(importlib, 'import_module', value)",
        "importlib.import_module(unknown)",
    ] {
        let found = client(
            &format!("import importlib\n{write}\nimportlib.import_module('app.service')\n"),
            "",
        );
        assert!(kinds(&found).contains(&"local"), "{write}");
        assert!(
            reasons(&found)
                .iter()
                .any(|reason| reason.starts_with("dynamic_import")),
            "{write}"
        );
    }
}

#[test]
fn a_local_literal_before_a_bound_loader_call_is_an_import() {
    let found = client(
        "import importlib\n\
         def load():\n    name = (\n        'app.service'\n    )\n    return importlib.import_module(name)\n",
        "",
    );
    assert_eq!(kinds(&found), ["builtin", "local"]);
    assert!(found.unknowns.is_empty(), "{:?}", reasons(&found));
}

#[test]
fn a_local_literal_with_an_unproven_path_or_loader_keeps_the_gap() {
    for source in [
        "import importlib\ndef outer():\n    name = 'app.service'\n    def load():\n        nonlocal name\n        return importlib.import_module(name)\n",
        "import importlib\ndef outer():\n    name = 'app.service'\n    def load():\n        return importlib.import_module(name)\n",
        "import importlib\ndef load(importlib):\n    name = 'app.service'\n    return importlib.import_module(name)\n",
        "import importlib\ndef load(flag):\n    if flag:\n        name = 'app.service'\n    return importlib.import_module(name)\n",
        "if flag:\n    import importlib\ndef load():\n    name = 'app.service'\n    return importlib.import_module(name)\n",
        "import importlib\ndef load():\n    name = 'app.service'\n    intervene()\n    return importlib.import_module(name)\n",
        "import importlib\ndef load():\n    name = 'app.service'\n    return importlib.import_module(name)\nimportlib.import_module = other\n",
    ] {
        let found = client(source, "");
        assert!(!found.imports.iter().any(|record|
            record.data.data().target_module.as_str() == "app.service"), "{source}");
        assert!(reasons(&found).iter().any(|reason|
            reason.starts_with("dynamic_import")), "{source}");
    }
}

#[test]
fn a_repository_file_that_shadows_importlib_keeps_the_gap() {
    let found = surveyed(&[
        ("src/importlib.py", "def import_module(name):\n    return None\n"),
        ("src/app/__init__.py", ""),
        ("src/app/client.py", "import importlib\ndef load():\n    name = 'app.service'\n    return importlib.import_module(name)\n"),
        ("src/app/service.py", ""),
    ]);
    assert!(!found
        .imports
        .iter()
        .any(|record| record.data.data().target_module.as_str() == "app.service"));
    assert!(reasons(&found)
        .iter()
        .any(|reason| reason.starts_with("dynamic_import")));
}

#[test]
fn a_literal_call_record_is_a_runtime_edge_also_under_a_guard() {
    // AD-472: the guard proof covers import statements only, so a literal call record is never
    // `under_type_checking`, also in the body of `if TYPE_CHECKING:` (the stricter reading).
    for source in [
        "__import__('app.service')\n",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    __import__('app.service')\n",
    ] {
        let found = client(source, "");
        let call = found
            .imports
            .iter()
            .find(|r| r.data.data().target_module.as_str() == "app.service");
        let data = call.expect("the call is an import record").data.data();
        assert!(!data.under_type_checking, "{source}");
    }
}

#[test]
fn source_roots_keep_python_names_and_resolve_siblings() {
    let found = surveyed_in(
        &[
            ("backend/__init__.py", ""),
            ("backend/worker/__init__.py", ""),
            ("backend/worker/task.py", "from shared import helper\nfrom . import support\nimport requests.adapters\nimport src.shared\n"),
            ("backend/worker/support.py", ""),
            ("backend/shared/__init__.py", ""),
            ("backend/shared/helper.py", ""),
        ],
        &["backend"],
        "",
    );
    let mut classes = kinds(&found);
    classes.sort_unstable();
    assert_eq!(classes, ["external", "external", "local", "local"]);
    assert!(reasons(&found).is_empty(), "{:?}", reasons(&found));
    assert!(found.targets.iter().any(|target| matches!(
        target,
        Target::Local { module, file, .. }
            if module.as_str() == "shared.helper" && file == "backend/shared/helper.py"
    )));
}

#[test]
fn ambiguous_source_root_providers_leave_a_gap() {
    for provider in ["", "def invalid(:\n"] {
        let found = surveyed_in(
            &[
                ("a/worker.py", "import shared.helper\n"),
                ("a/shared/__init__.py", ""),
                ("a/shared/helper.py", ""),
                ("b/shared/__init__.py", provider),
            ],
            &["a", "b"],
            "",
        );
        assert_eq!(kinds(&found), ["unresolved"]);
        assert!(reasons(&found)
            .iter()
            .any(|reason| reason.contains("duplicate_module")));
    }
}

#[test]
fn a_dotted_script_file_is_not_a_python_import_provider() {
    let found = surveyed_in(
        &[
            ("src/app.py", "import lib.values\n"),
            ("src/lib.values.py", ""),
        ],
        &["src"],
        "",
    );
    assert_eq!(kinds(&found), ["external"]);
}

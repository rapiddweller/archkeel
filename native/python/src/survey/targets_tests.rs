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
    survey_of(&Tree::new(files), roots, namespace)
}

/// The survey of an existing tree with the roots `src` and the namespace `app`.
pub(crate) fn surveyed_at(tree: &Tree) -> Survey {
    survey_of(tree, &["src"], "app")
}

fn survey_of(tree: &Tree, roots: &[&str], namespace: &str) -> Survey {
    let raw = json!({
        "protocol_version": "10.0.0",
        "snapshot": {"root": tree.path(), "git_head": "a".repeat(40), "dirty": false},
        "scope": {"roots": roots, "namespace": namespace, "exclude_test_sources": false},
        "resolver": {"language": "python", "phase": "imports", "interpreter": {
            "version": "3.14.0", "stdlib_module_names": ["json", "os", "sys"],
            "builtin_module_names": []}},
    });
    crate::survey::survey(&decode_python(raw.to_string().as_bytes()).unwrap()).unwrap()
}

pub(crate) fn surveyed(files: &[(&str, &str)]) -> Survey {
    surveyed_in(files, &["src"], "app")
}

/// The reason of each gap of a survey.
pub(crate) fn reasons(survey: &Survey) -> Vec<String> {
    survey.unknowns.iter().map(reason).collect()
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

/// The survey of `src/app/client.py` with `source`, beside `__init__.py` and `service.py`.
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

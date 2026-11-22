// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The name check of the exposure of a declared import (AD-1058). Each case has one construct in
//! one module, and `exposed_to` of the site `import pickle` in `app.service.model` must name that
//! module, so no check hides behind another one. The names of the other checks are absent.

use archkeel_facts::GapFact;

use crate::survey::targets::tests::surveyed;

const MODEL: (&str, &str) = ("src/app/service/model.py", "import pickle\n");
const INIT: (&str, &str) = ("src/app/service/__init__.py", "");

/// The modules that the site `import pickle` of `app.service.model` is exposed to, when
/// `app.service.other` holds `source` (and `extra` is one more file).
fn exposed(source: &str, extra: &[(&str, &str)]) -> Vec<String> {
    let mut files = vec![
        ("src/app/__init__.py", ""),
        INIT,
        MODEL,
        ("src/app/service/other.py", source),
    ];
    files.extend_from_slice(extra);
    let found = surveyed(&files);
    let mut sites = found.unknowns.iter().filter_map(|gap| match &gap.data {
        GapFact::SourceResolutionGap(data) => data.trojan_horse.as_ref().zip(data.module.as_ref()),
        _ => None,
    });
    let site = sites.find(|(site, module)| {
        module.as_str() == "app.service.model" && site.site_name.as_deref() == Some("pickle")
    });
    site.map(|(site, _)| site.exposed_to.clone())
        .unwrap_or_default()
}

fn names_other(source: &str, extra: &[(&str, &str)]) -> bool {
    exposed(source, extra)
        .iter()
        .any(|module| module == "app.service.other")
}

#[test]
fn an_attribute_of_the_name_exposes_the_binding() {
    assert!(names_other("def f(m):\n    return m.pickle\n", &[]));
}

#[test]
fn a_string_with_the_name_exposes_the_binding() {
    for text in ["pickle", "app.pickle", "pickle.loads"] {
        assert!(names_other(&format!("X = '{text}'\n"), &[]), "{text}");
    }
    assert!(!names_other("X = 'pickles'\n", &[]));
}

#[test]
fn an_import_of_the_name_exposes_the_binding() {
    assert!(names_other(
        "from app.service.model import pickle as p\n",
        &[]
    ));
    assert!(names_other("from elsewhere import pickle\n", &[]));
}

#[test]
fn a_star_import_of_the_module_or_of_a_module_that_imports_it_exposes_the_binding() {
    assert!(names_other("from app.service.model import *\n", &[]));
    let relay = ("src/app/service/relay.py", "import app.service.model\n");
    assert!(names_other("from app.service.relay import *\n", &[relay]));
}

#[test]
fn a_computed_read_of_any_attribute_exposes_the_binding() {
    for source in [
        "def f(m, n):\n    return getattr(m, n)\n",
        "def f(m):\n    return vars(m)\n",
        "def f(m):\n    return m.__dict__\n",
    ] {
        assert!(names_other(source, &[]), "{source}");
    }
}

#[test]
fn a_loader_call_with_a_computed_name_exposes_the_binding() {
    assert!(names_other(
        "import importlib\ndef f(n):\n    return importlib.import_module(n)\n",
        &[]
    ));
    assert!(!names_other(
        "import importlib\nM = importlib.import_module('json')\n",
        &[]
    ));
}

#[test]
fn a_plain_import_of_the_same_module_and_the_module_itself_do_not() {
    assert!(!names_other("import pickle\nX = 1\n", &[]));
    assert!(exposed("X = 1\n", &[]).is_empty());
}

/// The modules that the site `import pickle` is exposed to when the module itself reads as `home`.
fn exposed_by_home(home: &str) -> Vec<String> {
    let files = [
        ("src/app/__init__.py", ""),
        INIT,
        ("src/app/service/model.py", home),
    ];
    let found = surveyed(&files);
    let mut sites = found.unknowns.iter().filter_map(|gap| match &gap.data {
        GapFact::SourceResolutionGap(data) => data.trojan_horse.as_ref().zip(data.module.as_ref()),
        _ => None,
    });
    let site = sites
        .find(|(site, _)| site.site_name.as_deref() == Some("pickle") && site.binding.is_some());
    site.map(|(site, _)| site.exposed_to.clone())
        .unwrap_or_default()
}

#[test]
fn a_load_of_the_name_in_the_module_that_is_no_attribute_base_exposes_the_binding() {
    for home in [
        "import pickle\nHELPER = pickle\n",
        "import pickle\ndef __getattr__(n):\n    return pickle\n",
        "import pickle\nclass K:\n    p = pickle\n",
        "import pickle\ndef f(x=pickle):\n    return x\n",
        "import pickle\nITEMS = [pickle]\n",
        "import pickle\n__all__ = ['pickle']\n",
        "import pickle\ndef f():\n    return lambda: pickle\n",
        "import pickle\ndel pickle\n",
        "import pickle\ng = dict(m=pickle)\n",
    ] {
        assert_eq!(exposed_by_home(home), ["app.service.model"], "{home}");
    }
}

#[test]
fn a_use_of_the_name_as_the_base_of_an_attribute_does_not() {
    for home in [
        "import pickle\nX = pickle.dumps(1)\n",
        "import pickle\ndef f():\n    def g(b):\n        return pickle.loads(b)\n    return g\n",
        "import pickle\n",
        "import pickle\ndef f(x):\n    return pickle(x)\n",
    ] {
        assert!(exposed_by_home(home).is_empty(), "{home}");
    }
}

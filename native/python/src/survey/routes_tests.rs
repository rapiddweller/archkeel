// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `interface_boundary` reads the route of each named import (AD-504). A route is written
// only when each hop is proven; each form that makes a hop unproven must leave it empty, because
// an empty route is the named gap "unproven publication route" and never a verdict.

use super::*;
use crate::survey::targets::tests::surveyed;

/// The route of the import of `symbol` in `source`, after the resolution of the routes.
fn route(files: &[(&str, &str)], source: &str, symbol: &str) -> Option<Vec<String>> {
    let mut found = surveyed(files);
    resolve(&mut found.imports, &found.files, &found.opaque_surface);
    found.imports.iter().find_map(|record| {
        let data = record.data.data();
        (data.source_module.as_str() == source && data.symbol.as_deref() == Some(symbol))
            .then(|| data.reexport_chain.clone().unwrap_or_default())
    })
}

const INIT: &str = "src/app/pkg/__init__.py";
const USER: (&str, &str) = ("src/app/user.py", "from app.pkg import f\n");
const IMPL: (&str, &str) = ("src/app/pkg/impl.py", "def f(): pass\n");

fn through(init: &str) -> Option<Vec<String>> {
    route(
        &[("src/app/__init__.py", ""), (INIT, init), IMPL, USER],
        "app.user",
        "f",
    )
}

fn hops(names: &[&str]) -> Option<Vec<String>> {
    Some(names.iter().map(|name| (*name).to_owned()).collect())
}

#[test]
fn a_name_that_a_module_defines_has_one_hop() {
    let found = route(
        &[
            ("src/app/__init__.py", ""),
            ("src/app/b.py", "def f(): pass\n"),
            ("src/app/a.py", "from app.b import f\n"),
        ],
        "app.a",
        "f",
    );
    assert_eq!(found, hops(&["app.b.f"]));
}

#[test]
fn a_proven_reexport_of_a_package_adds_its_hop() {
    let init = "from app.pkg.impl import f\n\n__all__ = ['f']\n";
    assert_eq!(through(init), hops(&["app.pkg.f", "app.pkg.impl.f"]));
    // A package body that only imports re-exports without `__all__`.
    assert_eq!(
        through("from app.pkg.impl import f\n"),
        hops(&["app.pkg.f", "app.pkg.impl.f"])
    );
}

#[test]
fn a_dynamic_all_withholds_the_route() {
    for init in [
        "from app.pkg.impl import f\n__all__ = ['f'] + other\n",
        "from app.pkg.impl import f\n__all__ = ['f']\n__all__ += ['g']\n",
        "from app.pkg.impl import f\n__all__ = ['f']\n__all__.append('g')\n",
        "from app.pkg.impl import f\n__all__ = ['f']\n__all__ = ['f', 'g']\n",
        "from app.pkg.impl import f\nfrom app.other import __all__\n",
    ] {
        assert_eq!(through(init), Some(Vec::new()), "{init}");
    }
}

#[test]
fn a_binding_that_is_not_unique_withholds_the_route() {
    for init in [
        "from app.pkg.impl import f\ndef f(): pass\n",
        "try:\n    from app.pkg.impl import f\nexcept ImportError:\n    from app.pkg.other import f\n",
        "from app.pkg.impl import f\nf = 1\n",
    ] {
        assert_eq!(through(init), Some(Vec::new()), "{init}");
    }
}

#[test]
fn a_star_import_or_a_module_object_has_no_route() {
    let star = route(
        &[
            ("src/app/__init__.py", ""),
            ("src/app/b.py", "def f(): pass\n"),
            ("src/app/a.py", "from app.b import *\n"),
        ],
        "app.a",
        "*",
    );
    assert_eq!(star, Some(Vec::new()));
    let module = route(
        &[
            ("src/app/__init__.py", ""),
            ("src/app/b.py", ""),
            ("src/app/a.py", "from app import b\n"),
        ],
        "app.a",
        "b",
    );
    assert_eq!(module, None);
}

#[test]
fn the_survey_alone_writes_no_route() {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/b.py", "def f(): pass\n"),
        ("src/app/a.py", "from app.b import f\n"),
    ]);
    assert!(found
        .imports
        .iter()
        .all(|record| record.data.data().reexport_chain.is_none()));
}

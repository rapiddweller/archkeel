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
    resolve(
        &mut found.imports,
        &found.files,
        (&found.opaque_surface, &found.surface),
        (&found.sole_binders, &found.ambiguous),
        &found.sources,
    );
    found.imports.iter().find_map(|record| {
        let data = record.data.data();
        (data.source_module.as_str() == source && data.symbol.as_deref() == Some(symbol))
            .then(|| data.reexport_chain.clone().unwrap_or_default())
    })
}

/// The cause that the survey states for the withheld route of the import of `symbol`.
fn cause(
    files: &[(&str, &str)],
    source: &str,
    symbol: &str,
) -> Option<(RouteWithheld, Option<String>)> {
    let mut found = surveyed(files);
    resolve(
        &mut found.imports,
        &found.files,
        (&found.opaque_surface, &found.surface),
        (&found.sole_binders, &found.ambiguous),
        &found.sources,
    );
    found.imports.iter().find_map(|record| {
        let data = record.data.data();
        (data.source_module.as_str() == source && data.symbol.as_deref() == Some(symbol))
            .then(|| {
                data.route_withheld
                    .zip(Some(data.route_withheld_at.clone()))
            })
            .flatten()
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
fn an_import_that_is_not_a_plain_statement_of_the_body_is_no_reexport() {
    for init in [
        "def f(): pass\ndef _lazy():\n    from app.pkg.impl import f\n",
        "def f(): pass\nclass K:\n    from app.pkg.impl import f\n",
        "def f(): pass\ndef _lazy():\n    from .impl import f\n",
        "def f(): pass\ndef _lazy():\n    from app.pkg.impl import f as f\n",
        "def _lazy():\n    from app.pkg.impl import f\n    return f\ndef f(): pass\n",
        "try:\n    from app.pkg.impl import f\nexcept ImportError:\n    pass\n",
        "if True:\n    from app.pkg.impl import f\n",
        "from app.pkg.impl import f\nfor f in []:\n    pass\n",
    ] {
        assert_eq!(through(init), Some(Vec::new()), "{init}");
    }
}

#[test]
fn a_write_from_another_module_withholds_the_route() {
    let found = route(
        &[
            ("src/app/__init__.py", ""),
            (INIT, "from app.pkg.impl import f\nimport app.pkg._patch\n"),
            ("src/app/pkg/_patch.py", "from app import pkg\npkg.f = 1\n"),
            IMPL,
            USER,
        ],
        "app.user",
        "f",
    );
    assert_eq!(found, Some(Vec::new()));
}

#[test]
fn a_guarded_import_that_passes_a_reexport_has_no_route() {
    let guarded = route(
        &[
            ("src/app/__init__.py", ""),
            (INIT, "from app.pkg.impl import f\n"),
            IMPL,
            (
                "src/app/user.py",
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from app.pkg import f\n",
            ),
        ],
        "app.user",
        "f",
    );
    assert_eq!(guarded, Some(Vec::new()));
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

fn with_init(init: &str) -> Option<(RouteWithheld, Option<String>)> {
    cause(
        &[("src/app/__init__.py", ""), (INIT, init), IMPL, USER],
        "app.user",
        "f",
    )
}

#[test]
fn an_unread_all_is_the_stated_cause() {
    let found = with_init("from app.pkg.impl import f\n__all__ = ['f'] + other\n");
    assert_eq!(
        found,
        Some((RouteWithheld::UnreadAll, Some("app.pkg".to_owned())))
    );
}

#[test]
fn a_write_from_another_module_is_the_stated_cause() {
    let found = cause(
        &[
            ("src/app/__init__.py", ""),
            (INIT, "from app.pkg.impl import f\nimport app.pkg._patch\n"),
            ("src/app/pkg/_patch.py", "from app import pkg\npkg.f = 1\n"),
            IMPL,
            USER,
        ],
        "app.user",
        "f",
    );
    assert_eq!(
        found,
        Some((
            RouteWithheld::EscapedWrite,
            Some("app.pkg <- src/app/pkg/_patch.py:2".to_owned())
        ))
    );
}

#[test]
fn a_hop_that_is_not_unique_is_the_stated_cause() {
    let found = with_init("from app.pkg.impl import f\nf = 1\n");
    assert_eq!(
        found,
        Some((RouteWithheld::UncertainHop, Some("app.pkg.f".to_owned())))
    );
}

#[test]
fn a_guarded_reexport_is_the_stated_cause() {
    let found = cause(
        &[
            ("src/app/__init__.py", ""),
            (INIT, "from app.pkg.impl import f\n"),
            IMPL,
            (
                "src/app/user.py",
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from app.pkg import f\n",
            ),
        ],
        "app.user",
        "f",
    );
    assert_eq!(found, Some((RouteWithheld::TypeCheckingReexport, None)));
}

#[test]
fn a_proven_route_states_no_cause() {
    assert_eq!(with_init("from app.pkg.impl import f\n"), None);
}

#[test]
fn a_name_that_is_the_attribute_or_the_submodule_is_the_stated_cause() {
    let found = cause(
        &[
            ("src/app/__init__.py", ""),
            (INIT, "from app.pkg.impl import f\n"),
            ("src/app/pkg/f.py", "x = 1\n"),
            IMPL,
            USER,
        ],
        "app.user",
        "f",
    );
    assert_eq!(found, Some((RouteWithheld::AmbiguousReexport, None)));
}

#[test]
fn code_outside_the_scan_that_writes_a_module_is_the_stated_cause() {
    let found = cause(
        &[
            ("src/app/__init__.py", ""),
            (INIT, "from app.pkg.impl import f\n"),
            IMPL,
            USER,
            ("tools/patch.py", "import app.pkg\napp.pkg.f = 1\n"),
        ],
        "app.user",
        "f",
    );
    assert_eq!(
        found,
        Some((RouteWithheld::OutsideWrite, Some("app.pkg".to_owned())))
    );
}

/// The cause of the import of `f` from `app.pkg` when `other` is a module that uses `app.pkg`.
fn escaping_use(other: &str) -> Option<(RouteWithheld, Option<String>)> {
    cause(
        &[
            ("src/app/__init__.py", ""),
            (INIT, "from app.pkg.impl import f\n"),
            IMPL,
            USER,
            ("src/app/other.py", other),
        ],
        "app.user",
        "f",
    )
}

#[test]
fn a_module_handed_on_as_a_value_is_named_with_its_use() {
    let found = escaping_use("from app import pkg\nconsume(pkg)\n");
    assert_eq!(
        found,
        Some((
            RouteWithheld::EscapedValue,
            Some("app.pkg <- src/app/other.py:2".to_owned())
        ))
    );
}

#[test]
fn an_imported_name_of_unproven_kind_is_named_with_its_use() {
    let found = cause(
        &[
            ("src/app/__init__.py", ""),
            ("src/app/lib.py", "def f(): pass\nVALUE = factory()\n"),
            ("src/app/user.py", "from app.lib import f\n"),
            (
                "src/app/other.py",
                "from app.lib import VALUE\nconsume(VALUE)\n",
            ),
        ],
        "app.user",
        "f",
    );
    assert_eq!(
        found,
        Some((
            RouteWithheld::EscapedName,
            Some("app.lib <- src/app/other.py:2".to_owned())
        ))
    );
}

#[test]
fn a_namespace_read_is_named_with_its_use() {
    let found = escaping_use("from app import pkg\nnames = pkg.__dict__\n");
    assert_eq!(
        found,
        Some((
            RouteWithheld::EscapedNamespace,
            Some("app.pkg <- src/app/other.py:2".to_owned())
        ))
    );
}

#[test]
fn a_child_module_handed_on_is_named_with_its_use() {
    let found = cause(
        &[
            ("src/app/__init__.py", ""),
            (INIT, "from app.pkg.impl import f\n"),
            IMPL,
            USER,
            (
                "src/app/other.py",
                "from app import pkg\nconsume(pkg.impl)\n",
            ),
        ],
        "app.user",
        "f",
    );
    assert!(matches!(
        found,
        Some((RouteWithheld::EscapedChildModule, Some(at))) if at.ends_with("src/app/other.py:2")
    ));
}

#[test]
fn a_namespace_import_names_its_target_and_its_file() {
    let found = escaping_use("from app.pkg import __dict__ as names\n");
    assert_eq!(
        found,
        Some((
            RouteWithheld::EscapedNamespace,
            Some("app.pkg <- src/app/other.py (import of __dict__)".to_owned())
        ))
    );
}

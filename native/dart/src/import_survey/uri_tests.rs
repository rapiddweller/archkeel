// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the edges of the import survey (AD-454, rule 4). Each URI form has one class.

use super::{classify, generated, Uri};

fn local(rel: &str) -> Uri {
    Uri::Local(rel.to_owned())
}

#[test]
fn a_relative_uri_joins_the_directory_of_the_importer() {
    assert_eq!(
        classify("lib/a.dart", "b.dart", "shop"),
        local("lib/b.dart")
    );
    assert_eq!(
        classify("lib/src/a.dart", "../b.dart", "shop"),
        local("lib/b.dart")
    );
    assert_eq!(
        classify("lib/a.dart", "./x/../c.dart", "shop"),
        local("lib/c.dart")
    );
    assert_eq!(classify("lib/a.dart", "../../c.dart", "shop"), Uri::Outside);
}

#[test]
fn an_own_package_uri_gives_a_path_below_lib() {
    assert_eq!(
        classify("bin/m.dart", "package:shop/a.dart", "shop"),
        local("lib/a.dart")
    );
    assert_eq!(
        classify("lib/a.dart", "package:shop/../x.dart", "shop"),
        Uri::Outside
    );
}

#[test]
fn another_package_is_external_and_dart_is_builtin() {
    assert_eq!(
        classify("lib/a.dart", "package:http/src/client.dart", "shop"),
        Uri::External {
            package: "http".to_owned(),
            module: "http.src.client".to_owned()
        }
    );
    assert_eq!(
        classify("lib/a.dart", "DART:async", "shop"),
        Uri::Builtin("dart.async".to_owned())
    );
}

#[test]
fn without_a_package_name_no_package_uri_is_local() {
    assert!(matches!(
        classify("lib/a.dart", "package:shop/a.dart", ""),
        Uri::External { .. }
    ));
}

#[test]
fn each_other_form_is_unsupported() {
    let forms = [
        "",
        "http://x/a.dart",
        "file:///a.dart",
        "C:/a.dart",
        "/a.dart",
        "a.dart?x=1",
        "a.dart#f",
        "a%2Fb.dart",
        "a\\b.dart",
        "dart:core/x",
        "package:http",
        "package:http/",
        "package:9x/a.dart",
        "package:http/../a.dart",
    ];
    for form in forms {
        assert!(
            matches!(classify("lib/a.dart", form, "shop"), Uri::Unsupported(_)),
            "{form}"
        );
    }
}

#[test]
fn a_generated_file_has_one_of_two_suffixes() {
    assert!(generated("lib/a.g.dart"));
    assert!(generated("lib/a.freezed.dart"));
    assert!(!generated("lib/a.dart"));
}

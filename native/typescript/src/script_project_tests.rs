// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the script dependencies. The expected answers are those of
// `script_publication.stable_publication` and `source_origin` in Python; the integration tests
// (`tests/test_collector_native_script_deps.py`) compare whole projects.

use super::*;
use crate::script_types::ScriptGlobal;

fn at(line: i64) -> Span {
    Span {
        line,
        end_line: line,
        column: 1,
        excerpt: String::new(),
    }
}

fn published(line: i64, stable: bool, source_origin: bool) -> ScriptGlobal {
    ScriptGlobal {
        name: "Lib".to_owned(),
        span: at(line),
        members: Vec::new(),
        stable,
        source_members: Vec::new(),
        source_origin,
        availability: Vec::new(),
    }
}

#[test]
fn the_sole_write_is_the_one_write_of_the_name_or_of_no_known_name() {
    let (one, two, three) = (at(1), at(2), at(3));
    let by_name = WriteIndex::new([("a.js", Some("Lib"), &one), ("b.js", Some("Other"), &two)]);
    assert_eq!(by_name.sole("Lib"), Some(("a.js", &one)));
    assert_eq!(by_name.sole("Nothing"), None);
    let unknown = WriteIndex::new([("a.js", None, &three), ("b.js", Some("Lib"), &one)]);
    assert_eq!(
        unknown.sole("Lib"),
        None,
        "an unknown write counts for every name"
    );
    assert_eq!(unknown.sole("Other"), Some(("a.js", &three)));
    let twice = WriteIndex::new([("a.js", Some("Lib"), &one), ("a.js", Some("Lib"), &one)]);
    assert_eq!(twice.sole("Lib"), None);
}

#[test]
fn a_publication_is_stable_when_it_is_the_only_publisher_and_the_only_write() {
    let publication = published(1, true, false);
    let publishers = [("a.js", &publication)];
    let writes = WriteIndex::new([("a.js", Some("Lib"), &publication.span)]);
    assert!(stable_publication("Lib", &publishers, &writes));
    let other = at(9);
    let more = WriteIndex::new([
        ("a.js", Some("Lib"), &publication.span),
        ("b.js", Some("Lib"), &other),
    ]);
    assert!(!stable_publication("Lib", &publishers, &more));
    let moved = WriteIndex::new([("b.js", Some("Lib"), &publication.span)]);
    assert!(
        !stable_publication("Lib", &publishers, &moved),
        "the file counts"
    );
    let twice = [("a.js", &publication), ("b.js", &publication)];
    assert!(!stable_publication("Lib", &twice, &writes));
    assert!(!stable_publication("Lib", &[], &writes));
}

#[test]
fn a_source_origin_may_come_from_a_publication_that_is_not_stable() {
    let publication = published(1, false, true);
    let publishers = [("a.js", &publication)];
    let writes = WriteIndex::new([("a.js", Some("Lib"), &publication.span)]);
    assert!(source_origin("Lib", &publishers, &writes));
    assert!(!stable_publication("Lib", &publishers, &writes));
    let neither = published(1, false, false);
    assert!(!source_origin("Lib", &[("a.js", &neither)], &writes));
}

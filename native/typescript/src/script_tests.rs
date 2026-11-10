// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the walk. The expected values are the ones that `parse.parse()` of the Python
// collector gives for each source (`tests/test_collector_native_script_syntax.py` compares every
// script fact on a grid, on mutated sources and on real scripts).

use crate::parse::parse;
use crate::script_types::Script;
use crate::syntax::Parsers;

fn script(rel: &str, source: &str) -> Script {
    parse(&mut Parsers::new(), rel, source.as_bytes())
        .syntax
        .script
}

fn names(items: &[(Option<String>, crate::source::Span)]) -> Vec<Option<&str>> {
    items.iter().map(|(name, _)| name.as_deref()).collect()
}

#[test]
fn an_object_that_a_script_assigns_to_the_global_object_is_a_publication() {
    let found = script("a.js", "function run() {}\nwindow.Lib = { run };\n");
    assert_eq!(found.globals.len(), 1);
    let lib = &found.globals[0];
    assert_eq!(lib.name, "Lib");
    assert!(lib.stable && lib.source_origin);
    let members = |list: &[crate::script_types::Member]| -> Vec<(String, String)> {
        list.iter()
            .map(|(a, b, _)| (a.clone(), b.clone()))
            .collect()
    };
    assert_eq!(
        members(&lib.members),
        [("run".to_owned(), "run".to_owned())]
    );
    assert_eq!(members(&lib.source_members), members(&lib.members));
    assert_eq!(names(&found.writes), [Some("run"), Some("Lib")]);
    assert_eq!(found.write_paths, [["Lib"]]);
}

#[test]
fn a_publication_after_a_return_of_its_wrapper_is_not_stable() {
    let found = script(
        "a.js",
        "(function (g) { g.A = {}; return; g.B = {}; })(window);\n",
    );
    let stable: Vec<(&str, bool)> = found
        .globals
        .iter()
        .map(|item| (item.name.as_str(), item.stable))
        .collect();
    assert_eq!(stable, [("A", true), ("B", false)]);
    assert_eq!(found.globals[1].availability.len(), 1);
}

#[test]
fn a_namespace_pair_and_a_destructuring_are_found() {
    let namespace = "var NS;\n(function (NS) { NS.a = 1; })(NS || (NS = {}));\n";
    let found = script("a.js", namespace);
    assert_eq!(found.namespaces.len(), 1);
    assert_eq!(found.namespaces[0].name, "NS");
    assert_eq!(found.top_level_write_paths, [["NS"]]);
    let found = script("a.js", "const { a, b: c } = window.lib;\n");
    assert_eq!(found.destructures.len(), 1);
    let one = &found.destructures[0];
    assert_eq!(one.path, ["window", "lib"]);
    let locals: Vec<(&str, &str)> = one
        .members
        .iter()
        .map(|(key, local, _)| (key.as_str(), local.as_str()))
        .collect();
    assert_eq!(locals, [("a", "a"), ("b", "c")]);
}

#[test]
fn a_module_publishes_nothing_but_its_writes_are_known() {
    let found = script(
        "a.ts",
        "export const a = 1;\nwindow.X = { y };\nfunction y() {}\n",
    );
    assert!(found.globals.is_empty() && found.aliases.is_empty());
    assert!(names(&found.writes).contains(&Some("X")));
}

#[test]
fn a_call_through_a_computed_name_is_an_unknown_write() {
    let found = script("a.js", "window[k] = 1;\neval('x');\n");
    assert!(names(&found.writes).iter().all(Option::is_none));
    assert_eq!(found.writes.len(), 3);
}

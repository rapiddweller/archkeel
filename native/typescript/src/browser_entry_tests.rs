// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the browser scope of a part (AD-1420). `src/a.ts` reads `window.open` and `Math.max`.
// Without an entry, every script of the repository outside `src` is a possible writer. With an
// entry, only the files that the entry page loads are: a fixture that no entry loads is not code
// of the browser, and a file that the entry loads stays in. A reference that cannot be followed
// never narrows the scope: it holds every global and names the reference.

use archkeel_facts::request::BrowserSettings;
use archkeel_snapshot::test_tree::Tree;

use crate::collect::collect;
use crate::collect::tests::{provenance, request};

const A: &str =
    "window.open();\nwindow.close();\nwindow.print();\nexport const m = Math.max(1, 2);\n";
const PAGE: &str = "<!doctype html><script src=\"/boot.js\"></script>";

/// The titles of the gaps that withhold a global, for a page `web/index.html` that is the entry
/// when `browser` is set, and for the files of `outside`.
fn withheld(outside: &[(&str, &str)], browser: bool) -> Vec<String> {
    let mut files = vec![
        ("tsconfig.json", "{}"),
        ("src/a.ts", A),
        ("web/index.html", PAGE),
    ];
    files.extend_from_slice(outside);
    let tree = Tree::new(&files);
    let mut request = request(&tree, true);
    if browser {
        request.resolver.browser = Some(BrowserSettings {
            entry: "web/index.html".to_owned(),
            assets: vec!["web".to_owned()],
        });
    }
    collect(&request, provenance())
        .gaps
        .iter()
        .filter(|gap| gap.title.starts_with("Script global "))
        .map(|gap| gap.title.clone())
        .collect()
}

fn holds(titles: &[String], name: &str) -> bool {
    titles
        .iter()
        .any(|title| title.starts_with(&format!("Script global {name} ")))
}

const WRITES_OPEN: &str = "window.open = () => 1;\n";
const WRITES_CLOSE: &str = "window.close = () => 1;\n";

#[test]
fn a_file_that_the_entry_loads_is_browser_code_and_one_that_no_entry_loads_is_not() {
    let outside = [
        ("web/boot.js", WRITES_OPEN),
        ("tools/other.js", WRITES_CLOSE),
    ];
    let without = withheld(&outside, false);
    assert!(
        holds(&without, "open") && holds(&without, "close"),
        "control: both count"
    );
    let with = withheld(&outside, true);
    assert!(holds(&with, "open"), "the loaded writer stays in: {with:?}");
    assert!(
        !holds(&with, "close"),
        "the file no entry loads is out: {with:?}"
    );
}

#[test]
fn the_closure_follows_imports_and_relative_paths_transitively() {
    let boot = "import './js/main.js';\n";
    let main = "import './deep.js';\n";
    let outside = [
        ("web/boot.js", boot),
        ("web/js/main.js", main),
        ("web/js/deep.js", WRITES_OPEN),
        ("web/deep.js", WRITES_CLOSE),
    ];
    let with = withheld(&outside, true);
    assert!(
        holds(&with, "open"),
        "deep.js next to main.js is reached: {with:?}"
    );
    assert!(
        !holds(&with, "close"),
        "./deep.js is relative to /js/main.js: {with:?}"
    );
}

#[test]
fn an_unloaded_dynamic_and_worker_reference_are_followed_when_they_have_a_literal() {
    let boot = "import('/lazy.js');\nnew Worker(new URL('./w.js', import.meta.url));\n\
                importScripts('/legacy.js');\n";
    let outside = [
        ("web/boot.js", boot),
        ("web/lazy.js", WRITES_OPEN),
        ("web/w.js", "self.close = () => 1;\n"),
        ("web/legacy.js", "window.print = () => 1;\n"),
    ];
    let with = withheld(&outside, true);
    for name in ["open", "close", "print"] {
        assert!(
            holds(&with, name),
            "{name} is written by a loaded file: {with:?}"
        );
    }
}

#[test]
fn a_reference_that_cannot_be_followed_holds_every_global_and_never_narrows() {
    for (boot, cause) in [
        ("import '/missing.js';\n", "missing.js"),
        ("import('/a' + x);\n", "dynamic import with no literal path"),
        ("import 'lodash';\n", "bare name"),
        ("import '../../escape.js';\n", "in no assets folder"),
    ] {
        let titles = withheld(&[("web/boot.js", boot)], true);
        let held = titles
            .iter()
            .find(|title| title.starts_with("Script global Math has no native proof"));
        assert!(held.is_some(), "{boot}: Math is held: {titles:?}");
        let all = held.unwrap_or(&titles[0]);
        assert!(all.contains(cause), "{boot}: the cause is named: {all}");
    }
}

#[test]
fn a_remote_script_is_covered_by_the_premise_and_not_followed() {
    let page = "<script src=\"https://cdn.example/x.js\"></script>";
    let tree = Tree::new(&[
        ("tsconfig.json", "{}"),
        ("src/a.ts", A),
        ("web/index.html", page),
    ]);
    let mut request = request(&tree, true);
    request.resolver.browser = Some(BrowserSettings {
        entry: "web/index.html".to_owned(),
        assets: vec!["web".to_owned()],
    });
    let facts = collect(&request, provenance());
    assert!(!facts
        .gaps
        .iter()
        .any(|gap| gap.title.starts_with("Script global ")));
}

#[test]
fn the_page_reads_script_iframe_and_modulepreload_and_not_data_attributes() {
    let page = "<script data-src='/no.js'></script><script SRC=/yes.js defer></script>\
                <link rel=modulepreload href='/pre.js'><link rel=stylesheet href='/c.css'>\
                <iframe src=/frame.html></iframe><script>inline()</script>";
    let found = super::page_references("p.html", page.as_bytes());
    assert_eq!(found.found, ["/yes.js", "/pre.js", "/frame.html"]);
    assert!(found.incomplete.is_none());
}

#[test]
fn a_base_element_and_an_import_map_hold_every_global_because_they_change_what_a_path_means() {
    for page in [
        "<base href=/other/><script src=/boot.js></script>",
        "<script type=importmap>{\"imports\":{}}</script><script src=/boot.js></script>",
    ] {
        let found = super::page_references("p.html", page.as_bytes());
        assert!(found.incomplete.is_some(), "{page}");
    }
}

#[test]
fn code_that_makes_a_script_or_registers_a_worker_is_followed_or_holds_every_global() {
    // A script that a loaded file creates can load any file: the scope never narrows past it.
    for (boot, cause) in [
        (
            "document.createElement('script').src = '/x.js';\n",
            "script element that code creates",
        ),
        (
            "document.createElementNS(ns, 'script');\n",
            "script element that code creates",
        ),
        (
            "document.write('<script src=/x.js></script>');\n",
            "document.write",
        ),
        (
            "navigator.serviceWorker.register(path);\n",
            "service worker path that is no literal",
        ),
    ] {
        let titles = withheld(&[("web/boot.js", boot)], true);
        let held = titles
            .iter()
            .find(|title| title.starts_with("Script global Math has no native proof"));
        assert!(held.is_some(), "{boot}: Math is held: {titles:?}");
        assert!(
            held.is_some_and(|title| title.contains(cause)),
            "{boot}: {titles:?}"
        );
    }
    // A literal service worker is a loaded file; a div is no script.
    let boot = "navigator.serviceWorker.register('/sw.js');\ndocument.createElement('div');\n\
                document.createElement(tag);\n";
    let titles = withheld(&[("web/boot.js", boot), ("web/sw.js", WRITES_OPEN)], true);
    assert!(
        holds(&titles, "open"),
        "the service worker is read: {titles:?}"
    );
    assert!(
        titles
            .iter()
            .all(|title| !title.contains("no native proof")),
        "{titles:?}"
    );
}

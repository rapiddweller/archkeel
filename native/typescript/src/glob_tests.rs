// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: file discovery. Each row was printed by matching the regular expression of
// `config._wildcard(spec, ".", usage)` against the paths below, as `config._discover` matches.

use super::*;

const PATHS: [&str; 16] = [
    "/src/a.ts",
    "/src/b/c.ts",
    "/src/.hidden/c.ts",
    "/src/node_modules/c.ts",
    "/src/.a.ts",
    "/src/a.test.ts",
    "/src/b",
    "/src/node_modules",
    "/src",
    "/x/a.ts",
    "/src/xx.ts",
    "/src/.x.ts",
    "/a/b.min.js",
    "/a/b.js",
    "/a/.b.js",
    "/node_modules/a.ts",
];

#[rustfmt::skip]
const CASES: [(&str, Usage, &[&str]); 21] = [
    ("src/**/*.ts", Usage::Files, &["/src/a.ts", "/src/b/c.ts", "/src/a.test.ts", "/src/xx.ts"]),
    ("src/**/*.ts", Usage::Directories, &["/src/a.ts", "/src/b/c.ts", "/src/a.test.ts", "/src/b", "/src", "/src/xx.ts"]),
    ("src/**/*.ts", Usage::Exclude, &["/src/a.ts", "/src/b/c.ts", "/src/.hidden/c.ts", "/src/node_modules/c.ts", "/src/.a.ts", "/src/a.test.ts", "/src/xx.ts", "/src/.x.ts"]),
    ("src", Usage::Files, &["/src/a.ts", "/src/b/c.ts", "/src/a.test.ts", "/src/b", "/src/xx.ts"]),
    ("src", Usage::Directories, &["/src/a.ts", "/src/b/c.ts", "/src/a.test.ts", "/src/b", "/src", "/src/xx.ts"]),
    ("src", Usage::Exclude, &["/src/a.ts", "/src/b/c.ts", "/src/.hidden/c.ts", "/src/node_modules/c.ts", "/src/.a.ts", "/src/a.test.ts", "/src/b", "/src/node_modules", "/src", "/src/xx.ts", "/src/.x.ts"]),
    ("src/*.test.ts", Usage::Files, &["/src/a.test.ts"]),
    ("src/*.test.ts", Usage::Directories, &["/src/a.test.ts", "/src"]),
    ("src/*.test.ts", Usage::Exclude, &["/src/a.test.ts"]),
    ("**/*", Usage::Files, &["/src/a.ts", "/src/b/c.ts", "/src/a.test.ts", "/src/b", "/src", "/x/a.ts", "/src/xx.ts", "/a/b.js"]),
    ("**/*", Usage::Directories, &["/src/a.ts", "/src/b/c.ts", "/src/a.test.ts", "/src/b", "/src", "/x/a.ts", "/src/xx.ts", "/a/b.min.js", "/a/b.js"]),
    ("**/*", Usage::Exclude, &["/src/a.ts", "/src/b/c.ts", "/src/.hidden/c.ts", "/src/node_modules/c.ts", "/src/.a.ts", "/src/a.test.ts", "/src/b", "/src/node_modules", "/src", "/x/a.ts", "/src/xx.ts", "/src/.x.ts", "/a/b.min.js", "/a/b.js", "/a/.b.js", "/node_modules/a.ts"]),
    ("src/?x.ts", Usage::Files, &["/src/xx.ts"]),
    ("src/?x.ts", Usage::Directories, &["/src", "/src/xx.ts"]),
    ("src/?x.ts", Usage::Exclude, &["/src/xx.ts", "/src/.x.ts"]),
    ("a/*.js", Usage::Files, &["/a/b.js"]),
    ("a/*.js", Usage::Directories, &["/a/b.min.js", "/a/b.js"]),
    ("a/*.js", Usage::Exclude, &["/a/b.min.js", "/a/b.js", "/a/.b.js"]),
    (".", Usage::Files, &["/src/a.ts", "/src/b/c.ts", "/src/a.test.ts", "/src/b", "/src", "/x/a.ts", "/src/xx.ts", "/a/b.js"]),
    (".", Usage::Directories, &["/src/a.ts", "/src/b/c.ts", "/src/a.test.ts", "/src/b", "/src", "/x/a.ts", "/src/xx.ts", "/a/b.min.js", "/a/b.js"]),
    (".", Usage::Exclude, &["/src/a.ts", "/src/b/c.ts", "/src/.hidden/c.ts", "/src/node_modules/c.ts", "/src/.a.ts", "/src/a.test.ts", "/src/b", "/src/node_modules", "/src", "/x/a.ts", "/src/xx.ts", "/src/.x.ts", "/a/b.min.js", "/a/b.js", "/a/.b.js", "/node_modules/a.ts"]),
];

#[test]
fn patterns_select_what_the_python_regular_expressions_select() {
    for (spec, usage, expected) in CASES {
        let pattern = Pattern::new(spec, usage).unwrap();
        let selected: Vec<&str> = PATHS
            .into_iter()
            .filter(|path| pattern.matches(path))
            .collect();
        assert_eq!(selected, expected, "{spec} {usage:?}");
    }
}

#[test]
fn an_include_that_ends_in_a_recursive_wildcard_selects_nothing() {
    assert_eq!(Pattern::new("src/**", Usage::Files), None);
    assert!(Pattern::new("src/**", Usage::Exclude).is_some());
}

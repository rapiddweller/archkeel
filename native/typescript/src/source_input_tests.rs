// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: discovery and resolution. Each expected value is printed by `source_input.py`.

use super::*;

#[test]
fn files_classify_as_the_python_table() {
    let cases = [
        ("a.ts", Some(Ts), Some(("a", Ts))),
        ("a.d.ts", Some(Dts), Some(("a", Dts))),
        ("a.d.mts", Some(Dmts), Some(("a", Dmts))),
        ("b.x.js", Some(Js), Some(("b.x", Js))),
        ("a.json", Some(Json), Some(("a", Json))),
        ("a", Some(Absent), None),
        ("dir.v1/a", Some(Absent), None),
        ("a.css", None, None),
        ("a.d.json.ts", Some(Ts), Some(("a.d.json", Ts))),
        (".ts", Some(Ts), Some(("", Ts))),
        ("a.TS", None, None),
    ];
    for (name, suffix, parts) in cases {
        assert_eq!(classify_file(name), suffix, "{name}");
        assert_eq!(split_file(name), parts, "{name}");
    }
}

#[test]
fn a_suffix_has_the_replacements_of_its_family() {
    let ts = [SourceKind::TypeScript, SourceKind::Declaration];
    let js = [SourceKind::JavaScript];
    let all = [
        SourceKind::TypeScript,
        SourceKind::Declaration,
        SourceKind::JavaScript,
        SourceKind::Json,
    ];
    assert_eq!(Absent.replacements(&ts), [Ts, Tsx, Dts]);
    assert_eq!(Js.replacements(&js), [Js, Jsx]);
    assert_eq!(Mjs.replacements(&ts), [Mts, Dmts]);
    assert_eq!(Cts.replacements(&all), [Cts, Dcts, Cjs]);
    assert_eq!(Tsx.replacements(&ts), [Tsx, Ts, Dts]);
    assert_eq!(Jsx.replacements(&js), [Jsx, Js]);
    assert_eq!(Json.replacements(&ts), [JsonDeclaration]);
    assert_eq!(Json.replacements(&js), []);
    assert_eq!(Json.replacements(&all), [JsonDeclaration, Json]);
    assert_eq!(JsonDeclaration.replacements(&all), []);
}

#[test]
fn specifiers_classify_as_the_python_table() {
    use SpecifierKind::*;
    // text, kind, name, package, typed name, directory only, builtin, npm package, relative
    let cases = [
        (".", Current, ".", ".", ".", false, false, false, true),
        (
            "./a",
            CurrentPath,
            "./a",
            ".",
            "./a",
            false,
            false,
            false,
            true,
        ),
        (
            "../a", ParentPath, "../a", "..", "../a", false, false, false, true,
        ),
        (
            "/abs", Absolute, "/abs", "", "/abs", false, false, false, false,
        ),
        (
            "node:fs", Node, "fs", "node:fs", "node:fs", false, true, false, false,
        ),
        (
            "node:test",
            Node,
            "test",
            "node:test",
            "node:test",
            false,
            true,
            false,
            false,
        ),
        ("fs", Bare, "fs", "fs", "fs", false, true, true, false),
        (
            "@scope/pkg/sub",
            Scoped,
            "@scope/pkg/sub",
            "@scope/pkg",
            "scope__pkg/sub",
            false,
            false,
            true,
            false,
        ),
        (
            "@/lib", Scoped, "@/lib", "@/lib", "__lib", false, false, false, false,
        ),
        (
            "#imp", Imports, "#imp", "#imp", "#imp", false, false, false, false,
        ),
        (
            "lodash/", Bare, "lodash/", "lodash", "lodash/", true, false, true, false,
        ),
        ("@s", Scoped, "@s", "@s", "@s", false, false, false, false),
        (
            "@s/", Scoped, "@s/", "@s/", "s__", true, false, false, false,
        ),
        ("", Bare, "", "", "", false, false, false, false),
        (
            "test", Bare, "test", "test", "test", false, false, true, false,
        ),
        (
            "fs/promises",
            Bare,
            "fs/promises",
            "fs",
            "fs/promises",
            false,
            true,
            true,
            false,
        ),
        (
            "@types/node",
            Scoped,
            "@types/node",
            "@types/node",
            "types__node",
            false,
            false,
            true,
            false,
        ),
    ];
    for (text, kind, name, package, typed, directory, builtin, npm, relative) in cases {
        let found = classify_specifier(text);
        let got = (found.kind, found.name.as_str(), found.package.as_str());
        assert_eq!(got, (kind, name, package), "{text}");
        assert_eq!(found.typed_name, typed, "{text}");
        let flags = (
            found.directory_only,
            found.builtin(),
            found.npm_package(),
            found.relative(),
        );
        assert_eq!(flags, (directory, builtin, npm, relative), "{text}");
    }
}

#[test]
fn assets_classify_as_the_python_table() {
    let cases = [
        ("./a.css", Some("./a.css")),
        ("./a.CSS", None),
        ("./a.png?x", Some("./a.png")),
        ("./w.ts?worker", None),
        ("./w?worker", Some("./w")),
        ("./w?raw&x", Some("./w")),
        ("./.css", None),
        ("a/.css", None),
        ("./a.d.ts?url", None),
        ("./f.json", Some("./f.json")),
        ("./noext?url", Some("./noext")),
        ("x?", None),
    ];
    for (specifier, expected) in cases {
        assert_eq!(classify_asset(specifier), expected, "{specifier}");
    }
}

#[test]
fn a_higher_priority_sibling_shadows_a_file() {
    let known = |path: &str| ["a.ts", "a.js", "a.d.ts", "b.d.ts", "b.js", "c.mts"].contains(&path);
    assert!(shadowed("a.js", &known));
    assert!(shadowed("a.d.ts", &known));
    assert!(!shadowed("a.ts", &known));
    // A declaration does not shadow its JavaScript file.
    assert!(!shadowed("b.js", &known));
    assert!(!shadowed("c.mts", &known));
}

// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: import extraction, which must read the same references and concerns as
// `parse.parse`. Each expected value was printed by the Python function on the same source.

use serde_json::{json, Value};

use super::*;

const CASES: &str = r##"[
{"name": "forms", "file": "src/a.ts", "source": "import a from \"./a\";\nimport { b, type C } from './b';\nimport type { D } from \"./d\";\nimport * as ns from \"./ns\";\nimport \"./side\";\nimport e = require(\"./e\");\nimport type f = require(\"./f\");\nexport * from \"./g\";\nexport { h } from \"./h\";\nexport type { I } from \"./i\";\nexport * as j from \"./j\";\nconst k = await import(\"./k\");\ntype L = import(\"./l\").L;\nlet m: typeof import(\"./m\");\nconst n = require(\"./n\");\nconst o = require(p);\nconst q = import(`./q/${r}`);\nimport(/* c */ \"./s\");\nimport s2 from \"./esc\\u0041\";\nimport { type X, type Y } from \"./xy\";\nimport Z, { type W } from \"./zw\";\nimport w from \"./w\" with { \"resolution-mode\": \"require\" };\nif (x) { require(\"./inner\"); }\nexport { local };\nfunction f1(x: import(\"./t\").T) {}\nconst y1 = x as import(\"./v\").V;\nconst y2 = import(\"./v2\") as Promise<unknown>;\n", "expected": {"refs": [["import", "./a", false, true, false, 1, 1, 1, "import a from \"./a\";"], ["import", "./b", false, true, false, 2, 2, 1, "import { b, type C } from './b';"], ["import", "./d", true, true, false, 3, 3, 1, "import type { D } from \"./d\";"], ["import", "./ns", false, true, false, 4, 4, 1, "import * as ns from \"./ns\";"], ["import", "./side", false, true, false, 5, 5, 1, "import \"./side\";"], ["import_equals", "./e", false, true, false, 6, 6, 1, "import e = require(\"./e\");"], ["import_equals", "./f", true, true, false, 7, 7, 1, "import type f = require(\"./f\");"], ["reexport", "./g", false, true, false, 8, 8, 1, "export * from \"./g\";"], ["reexport", "./h", false, true, false, 9, 9, 1, "export { h } from \"./h\";"], ["reexport", "./i", true, true, false, 10, 10, 1, "export type { I } from \"./i\";"], ["reexport", "./j", false, true, false, 11, 11, 1, "export * as j from \"./j\";"], ["dynamic_import", "./k", false, false, false, 12, 12, 17, "import(\"./k\")"], ["import_type", "./l", true, false, false, 13, 13, 10, "import(\"./l\")"], ["import_type", "./m", true, false, false, 14, 14, 8, "typeof import(\"./m\")"], ["require", "./n", false, false, false, 15, 15, 11, "require(\"./n\")"], ["require", null, false, false, false, 16, 16, 11, "require(p)"], ["dynamic_import", null, false, false, false, 17, 17, 11, "import(`./q/${r}`)"], ["dynamic_import", null, false, false, false, 18, 18, 1, "import(/* c */ \"./s\")"], ["import", null, false, true, false, 19, 19, 1, "import s2 from \"./esc\\u0041\";"], ["import", "./xy", true, true, false, 20, 20, 1, "import { type X, type Y } from \"./xy\";"], ["import", "./zw", false, true, false, 21, 21, 1, "import Z, { type W } from \"./zw\";"], ["import", "./w", false, true, true, 22, 22, 1, "import w from \"./w\" with { \"resolution-mode\": \"require\" };"], ["require", "./inner", false, false, false, 23, 23, 10, "require(\"./inner\")"], ["import_type", "./t", true, false, false, 25, 25, 16, "import(\"./t\")"], ["import_type", "./v", true, false, false, 26, 26, 17, "import(\"./v\")"], ["dynamic_import", "./v2", false, false, false, 27, 27, 12, "import(\"./v2\")"]], "concerns": [], "shadows": false, "error": null}},
{"name": "positions", "file": "src/b.ts", "source": "const s = \"😀\"; import a from \"./😀\";\r\nimport b from './b'; import c from \"./c\"; \rimport d from \"./d\";\n\n  import e from \"./e\"\n", "expected": {"refs": [["import", "./😀", false, true, false, 1, 1, 17, "import a from \"./😀\";"], ["import", "./b", false, true, false, 2, 2, 1, "import b from './b';"], ["import", "./c", false, true, false, 3, 3, 1, "import c from \"./c\";"], ["import", "./d", false, true, false, 4, 4, 1, "import d from \"./d\";"], ["import", "./e", false, true, false, 6, 6, 3, "import e from \"./e\""]], "concerns": [], "shadows": false, "error": null}},
{"name": "errors", "file": "src/c.ts", "source": "import a from \"./a\";\nfunction ( {\nimport b from \"./b\";\nconst x = require(\"./x\");\n", "expected": {"refs": [["import", "./a", false, true, false, 1, 1, 1, "import a from \"./a\";"]], "concerns": [], "shadows": false, "error": 2}},
{"name": "require_concerns", "file": "src/d.ts", "source": "const r = require; r(\"./x\");\nconst { require: q } = module;\nconst key = \"req\"; const z = module[key];\ntypeof require; require.main; require[\"main\"]; module[\"require\"];\nconst m = require(\"module\");\nconst { [dyn]: v } = module;\nconst { \"require\": w2 } = module;\nfunction f(require) {}\n", "expected": {"refs": [["require", "module", false, false, false, 5, 5, 11, "require(\"module\")"]], "concerns": [["Computed require member use", 3, 3, 30, "module[key]"], ["Computed require member use", 4, 4, 48, "module[\"require\"]"], ["Indirect require binding is not resolved", 2, 2, 9, "require: q"], ["Indirect require binding is not resolved", 6, 6, 9, "[dyn]: v"], ["Indirect require binding is not resolved", 7, 7, 9, "\"require\": w2"], ["Indirect require use is not resolved", 1, 1, 11, "require"], ["Indirect require use is not resolved", 4, 4, 8, "require"], ["Indirect require use is not resolved", 4, 4, 17, "require"], ["Indirect require use is not resolved", 4, 4, 31, "require"], ["Indirect require use is not resolved", 8, 8, 12, "require"], ["Node module loader is not observed", 5, 5, 11, "require(\"module\")"]], "shadows": true, "error": null}},
{"name": "create_require", "file": "src/e.mts", "source": "import { createRequire } from \"node:module\";\nconst req = createRequire(import.meta.url);\n", "expected": {"refs": [["import", "node:module", false, true, false, 1, 1, 1, "import { createRequire } from \"node:module\";"]], "concerns": [["Node module loader is not observed", 1, 1, 1, "import { createRequire } from \"node:module\";"]], "shadows": false, "error": null}},
{"name": "comments_ts", "file": "src/f.ts", "source": "/// <reference path=\"./p.d.ts\" />\n/// <reference lib=\"es2020\" />\n/// <reference types=\"node\" />\n/** @import { T } from \"./t\" */\n/** @type {import(\"./x\").Y} */\nexport const a = 1;\n/// <reference path=\"./late.d.ts\" />\n", "expected": {"refs": [], "concerns": [["Unobserved triple-slash reference: ./p.d.ts", 1, 1, 1, "/// <reference path=\"./p.d.ts\" />"], ["Unobserved triple-slash reference: es2020", 2, 2, 1, "/// <reference lib=\"es2020\" />"]], "shadows": false, "error": null}},
{"name": "comments_js", "file": "src/g.js", "source": "/// <reference path=\"./p.d.ts\" />\n/** @import { T } from \"./t\" */\n/** @type {import(\"./x\").Y} */\n/** prose: import(x) is only text */\n/** @param {string} a @returns {import(\"./z\").Z} */\n/** @template [T=import(\"./d\")] */\n/** @typedef {{ a: \"}\" }} Q */\n/* import(\"./nope\") */\nconst a = 1;\n", "expected": {"refs": [], "concerns": [["JSDoc import is not observed", 2, 2, 1, "/** @import { T } from \"./t\" */"], ["JSDoc import is not observed", 3, 3, 1, "/** @type {import(\"./x\").Y} */"], ["JSDoc import is not observed", 5, 5, 1, "/** @param {string} a @returns {import(\"./z\").Z} */"], ["JSDoc import is not observed", 6, 6, 1, "/** @template [T=import(\"./d\")] */"], ["Unobserved triple-slash reference: ./p.d.ts", 1, 1, 1, "/// <reference path=\"./p.d.ts\" />"]], "shadows": false, "error": null}},
{"name": "tsx", "file": "src/h.tsx", "source": "import React from \"react\";\nconst a = <T,>(x: T) => x;\nconst b = <div onClick={() => import(\"./lazy\")}>{require(\"./r\")}</div>;\n", "expected": {"refs": [["import", "react", false, true, false, 1, 1, 1, "import React from \"react\";"], ["dynamic_import", "./lazy", false, false, false, 3, 3, 31, "import(\"./lazy\")"], ["require", "./r", false, false, false, 3, 3, 50, "require(\"./r\")"]], "concerns": [], "shadows": false, "error": null}},
{"name": "assertion", "file": "src/i.ts", "source": "const a = <Foo>bar;\nimport b from \"./b\";\n", "expected": {"refs": [["import", "./b", false, true, false, 2, 2, 1, "import b from \"./b\";"]], "concerns": [], "shadows": false, "error": null}},
{"name": "script", "file": "src/j.js", "source": "var a = require(\"./a\");\nwindow.foo = 1;\nimport(\"./b\");\n", "expected": {"refs": [["require", "./a", false, false, false, 1, 1, 9, "require(\"./a\")"], ["dynamic_import", "./b", false, false, false, 3, 3, 1, "import(\"./b\")"]], "concerns": [], "shadows": false, "error": null}},
{"name": "unicode_replacement", "file": "src/k.ts", "source": "import a from \"./a�\";\nimport b from \"./b\";\n", "expected": {"refs": [["import", "./a�", false, true, false, 1, 1, 1, "import a from \"./a�\";"], ["import", "./b", false, true, false, 2, 2, 1, "import b from \"./b\";"]], "concerns": [], "shadows": false, "error": null}},
{"name": "empty", "file": "src/l.ts", "source": "", "expected": {"refs": [], "concerns": [], "shadows": false, "error": null}},
{"name": "newline_name", "file": "src/m.ts\n", "source": "import a from \"./a\";\n", "expected": {"refs": [["import", "./a", false, true, false, 1, 1, 1, "import a from \"./a\";"]], "concerns": [], "shadows": false, "error": null}}
]"##;

fn render(parsed: &Parsed) -> Value {
    let refs: Vec<Value> = parsed
        .references
        .iter()
        .map(|r| {
            let span = &r.span;
            json!([
                r.form.as_str(),
                r.specifier,
                r.type_only,
                r.module_level,
                r.mode_override,
                span.line,
                span.end_line,
                span.column,
                span.excerpt
            ])
        })
        .collect();
    let mut concerns: Vec<Value> = parsed
        .concerns
        .iter()
        .map(|c| {
            json!([
                c.reason,
                c.span.line,
                c.span.end_line,
                c.span.column,
                c.span.excerpt
            ])
        })
        .collect();
    concerns.sort_by_key(Value::to_string);
    concerns.dedup();
    json!({"refs": refs, "concerns": concerns, "shadows": parsed.shadows_require, "error": parsed.first_error})
}

#[test]
fn references_and_concerns_match_the_python_parser() {
    let cases: Vec<Value> = serde_json::from_str(CASES).expect("the cases are JSON");
    let mut parsers = Parsers::new();
    for case in cases {
        let name = case["name"].as_str().expect("a name");
        let source = case["source"].as_str().expect("a source");
        let parsed = parse(
            &mut parsers,
            case["file"].as_str().expect("a file"),
            source.as_bytes(),
        );
        let mut expected = case["expected"].clone();
        let sorted = |value: &mut Value| {
            if let Some(list) = value.as_array_mut() {
                list.sort_by_key(Value::to_string);
                list.dedup();
            }
        };
        sorted(&mut expected["concerns"]);
        assert_eq!(render(&parsed), expected, "{name}");
    }
}

// A generator with a fixed seed (no extra crate): the extractor must give a result, never panic.
struct Seeded(u64);

impl Seeded {
    fn next(&mut self) -> u64 {
        // xorshift64*
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_f491_4f6c_dd1d)
    }

    fn below(&mut self, limit: usize) -> usize {
        (self.next() % limit as u64) as usize
    }
}

const FRAGMENTS: [&str; 24] = [
    "import a from \"./a\";",
    "import { b, type C } from './b'",
    "export * from \"./c\"",
    "const d = require(\"./d\")",
    "await import(`./${e}`)",
    "type T = import(\"./t\").T",
    "/** @import { X } from './x' */",
    "/// <reference path=\"./p.d.ts\" />",
    "const { require: r } = module",
    "module[\"req\" + \"uire\"]",
    "<div>{x}</div>",
    "<T>y",
    "class A<T extends import('./z').Z> {",
    "}}",
    "((((",
    "`${",
    "/*",
    "\"",
    "\\",
    "\u{2028}",
    "\r\n",
    "😀",
    "\u{feff}",
    "@",
];

#[test]
fn random_sources_never_panic() {
    let mut parsers = Parsers::new();
    let mut random = Seeded(0x880);
    for round in 0..1500 {
        let mut text = String::new();
        for _ in 0..random.below(12) {
            text.push_str(FRAGMENTS[random.below(FRAGMENTS.len())]);
            text.push(['\n', ' ', ';'][random.below(3)]);
        }
        // Cut inside a character, as a damaged file does, and keep the bytes as they are.
        let mut bytes = text.into_bytes();
        if round % 3 == 0 && !bytes.is_empty() {
            bytes.truncate(random.below(bytes.len()));
        }
        let names = [
            "a.ts", "a.tsx", "a.js", "a.jsx", "a.mts", "a.d.ts", "a.json", "a",
        ];
        let lossy = String::from_utf8_lossy(&bytes).into_owned();
        let parsed = parse(
            &mut parsers,
            names[random.below(names.len())],
            lossy.as_bytes(),
        );
        assert!(parsed.references.len() <= lossy.len() + 1);
    }
}

#[test]
fn deep_and_long_sources_give_a_result() {
    let mut parsers = Parsers::new();
    let nested = format!("const a = {}1{};", "(".repeat(4000), ")".repeat(4000));
    let long = format!("import a from './{}';", "x".repeat(1_000_000));
    let comment = format!("/**{}import('./a')*/", " @type {".repeat(3000));
    for text in [nested, long, comment] {
        parse(&mut parsers, "a.ts", text.as_bytes());
        parse(&mut parsers, "a.js", text.as_bytes());
    }
}

fn corpus(directory: &std::path::Path, found: &mut Vec<Vec<u8>>) {
    let Ok(entries) = std::fs::read_dir(directory) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            corpus(&path, found);
        } else if path
            .extension()
            .is_some_and(|ext| ext == "ts" || ext == "tsx")
        {
            found.extend(std::fs::read(&path));
        }
    }
}

#[test]
fn mutated_real_sources_never_panic() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../");
    let mut sources = Vec::new();
    corpus(&root.join("fixtures/L-nest-realworld/src"), &mut sources);
    corpus(&root.join("src/archkeel/studio/ui"), &mut sources);
    assert!(sources.len() > 40, "the real sources are missing");
    let mut parsers = Parsers::new();
    let mut random = Seeded(0x4_2880);
    for source in &sources {
        for round in 0..30 {
            let mut bytes = source.clone();
            let at = random.below(bytes.len().max(1));
            match round % 6 {
                // A flipped byte, a deleted range, a repeated range, a cut, a stray token, a NUL.
                0 => {
                    let last = bytes.len() - 1;
                    bytes[at.min(last)] ^= 1 << random.below(8);
                }
                1 => drop(bytes.drain(at..bytes.len().min(at + random.below(64)))),
                2 => {
                    let end = bytes.len().min(at + 200);
                    let copy: Vec<u8> = bytes[at..end].to_vec();
                    bytes.splice(at..at, copy);
                }
                3 => bytes.truncate(at),
                4 => {
                    let token = FRAGMENTS[random.below(FRAGMENTS.len())].as_bytes().to_vec();
                    bytes.splice(at..at, token);
                }
                _ => bytes.insert(at, 0),
            }
            let lossy = String::from_utf8_lossy(&bytes).into_owned();
            let name = if round % 2 == 0 { "a.ts" } else { "a.tsx" };
            parse(&mut parsers, name, lossy.as_bytes());
        }
    }
}

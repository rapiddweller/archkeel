// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: import resolution, which must name the same file as `resolve.Resolver`. Every
// expected line was printed by the Python resolver on the same tree. A line has the importer, the
// specifier, the mode, `prefer_builtin` and the result; `;` separates the fields.

use super::*;
use crate::config::load_config;
use crate::test_tree::Tree;

// Each block: name, config, blocked reason, resolutions, formats, reads, problems.
const TREE: &[(&str, &str)] = &[
    ("src/main.ts", ""),
    ("src/util.ts", ""),
    ("src/util.js", ""),
    ("src/dir/index.ts", ""),
    ("src/esm.mts", ""),
    ("src/cjs.cts", ""),
    ("src/pkgdir/package.json", "{\"main\":\"./lib/entry.js\"}"),
    ("src/pkgdir/lib/entry.ts", ""),
    ("src/data.json", "{}"),
    ("src/types.d.ts", ""),
    ("src/app/x.ts", ""),
    ("src/lib/index.ts", ""),
    ("src/only.js", ""),
    ("src/ts-vs-js/a.js", ""),
    ("src/ts-vs-js/a.d.ts", ""),
    ("src/badpkg/package.json", "{nope"),
    ("src/arr/package.json", "[1]"),
    ("src/tv/package.json", "{\"typesVersions\":{\"*\":{\"*\":[\"x\"]}}}"),
    ("src/tv/index.ts", ""),
    ("package.json", "{\"name\":\"app\",\"type\":\"module\",\"exports\":\"./x.js\"}"),
    ("node_modules/pkg-a/package.json", "{\"main\":\"main.js\",\"types\":\"main.d.ts\"}"),
    ("node_modules/pkg-a/main.d.ts", ""),
    ("node_modules/pkg-a/main.js", ""),
    ("node_modules/pkg-a/sub/deep.d.ts", ""),
    ("node_modules/pkg-b/package.json", "{\"exports\":{\".\":{\"types\":\"./index.d.ts\",\"import\":\"./index.mjs\",\"require\":\"./index.cjs\"},\"./sub\":\"./sub.js\",\"./asset\":\"./a.css\",\"./bad\":\"../x.js\",\"./cond\":{\"node\":\"./n.js\"}}}"),
    ("node_modules/pkg-b/index.d.ts", ""),
    ("node_modules/pkg-b/sub.d.ts", ""),
    ("node_modules/pkg-b/sub.js", ""),
    ("node_modules/pkg-b/a.css", ""),
    ("node_modules/@types/lodash/index.d.ts", ""),
    ("node_modules/@types/scope__thing/index.d.ts", ""),
    ("node_modules/@scope/pkg-c/package.json", "{\"typesVersions\":{\"*\":{\"*\":[\"ts/*\"]}}}"),
    ("node_modules/@scope/pkg-c/index.d.ts", ""),
    ("node_modules/pkg-d/package.json", "{\"exports\":{\"./*\":\"./*.js\"}}"),
    ("node_modules/pkg-d/x.js", ""),
    ("node_modules/pkg-e/package.json", "{\"exports\":\"./e.js\"}"),
    ("node_modules/pkg-e/e.js", ""),
    ("node_modules/pkg-f/package.json", "{\"exports\":{\"import\":\"./f.mjs\",\"default\":\"./f.js\"}}"),
    ("node_modules/pkg-f/f.mjs", ""),
    ("node_modules/pkg-f/f.js", ""),
    ("node_modules/pkg-g/package.json", "{\"exports\":{\".\":\"./g.js\",\"x\":\"./x.js\"}}"),
    ("node_modules/pkg-h/package.json", "{\"type\":\"module\",\"main\":\"h\"}"),
    ("node_modules/pkg-h/h.js", ""),
    ("node_modules/pkg-h/index.js", ""),
    ("node_modules/pkg-i/package.json", "{}"),
    ("node_modules/pkg-i/index.js", ""),
    ("node_modules/pkg-j/package.json", "{\"exports\":{\"./a\":null,\"./b/*\":\"./b/*.js\"}}"),
    ("node_modules/pkg-k/package.json", "{\"exports\":{\".\":{\"weird\":\"./k.js\"}}}"),
    ("node_modules/pkg-l/package.json", "{\"exports\":{\".\":{\"default\":{\"import\":\"./l.js\"}}}}"),
    ("node_modules/pkg-l/l.js", ""),
    ("node_modules/pkg-m/package.json", "{\"exports\":{\".\":\"/abs.js\",\"./a\":\"./a/../b.js\",\"./c\":\"./c%20.js\",\"./d\":\"./.js\"}}"),
    ("node_modules/pkg-n/package.json", "{\"exports\":{\".\":7,\"./a\":true}}"),
    ("node_modules/pkg-o/package.json", "{\"exports\":[\"./o.js\"]}"),
    ("node_modules/pkg-p/package.json", "{\"exports\":{\"a\":\"./a.js\",\"./b\":\"./b.js\"}}"),
];

const NODE10: &str = r#"
config|{"compilerOptions":{"baseUrl":".","paths":{"@app/*":["src/app/*"],"@lib":["src/lib/index.ts"],"@abs":["/abs"],"@json/*":["src/*.json"]},"resolveJsonModule":true,"module":"commonjs"},"include":["src"]}
blocked|-
src/main.ts;./util;-;0;found;src/util.ts;0;0;0
src/main.ts;./util.js;-;0;found;src/util.ts;0;0;0
src/main.ts;./util.ts;-;0;found;src/util.ts;0;0;0
src/main.ts;./dir;-;0;found;src/dir/index.ts;0;0;0
src/main.ts;./dir/;-;0;found;src/dir/index.ts;0;0;0
src/main.ts;./esm.js;-;0;missing
src/main.ts;./cjs.js;-;0;missing
src/main.ts;./pkgdir;-;0;found;src/pkgdir/lib/entry.ts;0;1;0
src/main.ts;./pkgdir/;-;0;found;src/pkgdir/lib/entry.ts;0;1;0
src/main.ts;./data;-;0;missing
src/main.ts;./data.json;-;0;found;src/data.json;0;0;0
src/main.ts;./types;-;0;found;src/types.d.ts;0;0;0
src/main.ts;./app/x;-;0;found;src/app/x.ts;0;0;0
src/main.ts;./missing;-;0;missing
src/main.ts;../src/util;-;0;found;src/util.ts;0;0;0
src/main.ts;.;-;0;missing
src/main.ts;..;-;0;missing
src/main.ts;./ts-vs-js/a;-;0;found;src/ts-vs-js/a.d.ts;0;0;0
src/main.ts;./only;-;0;found;src/only.js;0;0;0
src/main.ts;./only.js;-;0;found;src/only.js;0;0;0
src/main.ts;./badpkg;-;0;unknown;Package metadata is not valid JSON: src/badpkg/package.json;0
src/main.ts;./arr;-;0;unknown;Package metadata is not an object: src/arr/package.json;0
src/main.ts;./tv;-;0;unknown;Package typesVersions are not observed: src/tv;0
src/main.ts;./esm;-;0;missing
src/main.ts;./cjs;-;0;missing
src/main.ts;@app/x;-;0;found;src/app/x.ts;0;0;1
src/main.ts;@lib;-;0;found;src/lib/index.ts;0;0;1
src/main.ts;@abs;-;0;unknown;Absolute paths targets are not observed: @abs;0
src/main.ts;@json/data;-;0;found;src/data.json;0;0;1
src/main.ts;~/util;-;0;missing
src/main.ts;~/dir;-;0;missing
src/main.ts;#internal;-;0;missing
src/main.ts;app;-;0;missing
src/main.ts;app/sub;-;0;missing
src/main.ts;/abs/x;-;0;unknown;Absolute specifiers are not observed: /abs/x;0
src/main.ts;pkg-a;-;0;found;node_modules/pkg-a/main.d.ts;1;0;0
src/main.ts;pkg-a/sub/deep;-;0;found;node_modules/pkg-a/sub/deep.d.ts;1;0;0
src/main.ts;pkg-a/sub/deep.js;-;0;found;node_modules/pkg-a/sub/deep.d.ts;1;0;0
src/main.ts;pkg-b;-;0;found;node_modules/pkg-b/index.d.ts;1;0;0
src/main.ts;pkg-b/sub;-;0;found;node_modules/pkg-b/sub.d.ts;1;0;0
src/main.ts;pkg-b/asset;-;0;missing
src/main.ts;pkg-b/bad;-;0;missing
src/main.ts;pkg-b/cond;-;0;missing
src/main.ts;pkg-b/nope;-;0;missing
src/main.ts;lodash;-;0;found;node_modules/@types/lodash/index.d.ts;1;0;0
src/main.ts;lodash/fp;-;0;missing
src/main.ts;scope__thing;-;0;found;node_modules/@types/scope__thing/index.d.ts;1;0;0
src/main.ts;@scope/thing;-;0;found;node_modules/@types/scope__thing/index.d.ts;1;0;0
src/main.ts;@scope/pkg-c;-;0;unknown;Package typesVersions are not observed: @scope/pkg-c;1
src/main.ts;@scope/pkg-c/x;-;0;unknown;Package typesVersions are not observed: @scope/pkg-c;1
src/main.ts;pkg-d/x;-;0;found;node_modules/pkg-d/x.js;1;0;0
src/main.ts;pkg-d/y;-;0;missing
src/main.ts;pkg-e;-;0;missing
src/main.ts;pkg-e/x;-;0;missing
src/main.ts;pkg-f;-;0;missing
src/main.ts;pkg-g;-;0;missing
src/main.ts;pkg-g/x;-;0;missing
src/main.ts;pkg-g/y;-;0;missing
src/main.ts;pkg-h;-;0;found;node_modules/pkg-h/h.js;1;0;0
src/main.ts;pkg-i;-;0;found;node_modules/pkg-i/index.js;1;0;0
src/main.ts;pkg-j/a;-;0;missing
src/main.ts;pkg-j/b/z;-;0;missing
src/main.ts;pkg-j/c;-;0;missing
src/main.ts;pkg-k;-;0;missing
src/main.ts;pkg-l;-;0;missing
src/main.ts;pkg-m;-;0;missing
src/main.ts;pkg-m/a;-;0;missing
src/main.ts;pkg-m/c;-;0;missing
src/main.ts;pkg-m/d;-;0;missing
src/main.ts;pkg-n;-;0;missing
src/main.ts;pkg-n/a;-;0;missing
src/main.ts;pkg-o;-;0;missing
src/main.ts;pkg-p;-;0;missing
src/main.ts;pkg-p/b;-;0;missing
src/main.ts;fs;-;0;missing
src/main.ts;node:fs;-;0;missing
src/main.ts;fs/promises;-;0;missing
src/main.ts;node:test;-;0;missing
src/main.ts;sea;-;0;missing
src/main.ts;nope-pkg;-;0;missing
src/app/x.ts;./x;-;0;found;src/app/x.ts;0;0;0
src/app/x.ts;../util;-;0;found;src/util.ts;0;0;0
src/app/x.ts;pkg-a;-;0;found;node_modules/pkg-a/main.d.ts;1;0;0
src/app/x.ts;@app/x;-;0;found;src/app/x.ts;0;0;1
reads|node_modules/@scope/pkg-c/package.json,node_modules/pkg-a/package.json,node_modules/pkg-b/package.json,node_modules/pkg-d/package.json,node_modules/pkg-e/package.json,node_modules/pkg-f/package.json,node_modules/pkg-g/package.json,node_modules/pkg-h/package.json,node_modules/pkg-i/package.json,node_modules/pkg-j/package.json,node_modules/pkg-k/package.json,node_modules/pkg-l/package.json,node_modules/pkg-m/package.json,node_modules/pkg-n/package.json,node_modules/pkg-o/package.json,node_modules/pkg-p/package.json,package.json,src/arr/package.json,src/badpkg/package.json,src/pkgdir/package.json,src/tv/package.json,tsconfig.json
problems|-
"#;

const BUNDLER: &str = r#"
config|{"compilerOptions":{"module":"esnext","moduleResolution":"bundler","paths":{"~/*":["./src/*"]}},"include":["src"]}
blocked|-
src/main.ts;./util;-;0;found;src/util.ts;0;0;0
src/main.ts;./dir;-;0;found;src/dir/index.ts;0;0;0
src/main.ts;~/util;-;0;found;src/util.ts;0;0;1
src/main.ts;~/dir;-;0;found;src/dir/index.ts;0;0;1
src/main.ts;pkg-a;-;0;found;node_modules/pkg-a/main.d.ts;1;0;0
src/main.ts;pkg-b;-;0;found;node_modules/pkg-b/index.d.ts;1;0;0
src/main.ts;pkg-b/asset;-;0;unknown;Package exports target is an asset: pkg-b/asset;1
src/main.ts;pkg-b/sub;-;0;found;node_modules/pkg-b/sub.d.ts;1;0;0
src/main.ts;@lib;-;0;missing
src/main.ts;fs;-;0;missing
src/main.ts;missing;-;0;missing
reads|node_modules/pkg-a/package.json,node_modules/pkg-b/package.json,package.json,tsconfig.json
problems|-
"#;

const NODENEXT: &str = r#"
config|{"compilerOptions":{"module":"nodenext","moduleResolution":"nodenext"},"include":["src"]}
blocked|-
src/main.ts;./util.js;-;0;found;src/util.ts;0;0;0
src/main.ts;./util.js;-;1;found;src/util.ts;0;0;0
src/main.ts;./esm.js;-;0;missing
src/main.ts;./esm.js;-;1;missing
src/main.ts;./dir;-;0;found;src/dir/index.ts;0;0;0
src/main.ts;./dir;-;1;found;src/dir/index.ts;0;0;0
src/main.ts;pkg-a;-;0;found;node_modules/pkg-a/main.d.ts;1;0;0
src/main.ts;pkg-a;-;1;found;node_modules/pkg-a/main.d.ts;1;0;0
src/main.ts;pkg-b;-;0;found;node_modules/pkg-b/index.d.ts;1;0;0
src/main.ts;pkg-b;-;1;found;node_modules/pkg-b/index.d.ts;1;0;0
src/main.ts;pkg-b/sub;-;0;found;node_modules/pkg-b/sub.d.ts;1;0;0
src/main.ts;pkg-b/sub;-;1;found;node_modules/pkg-b/sub.d.ts;1;0;0
src/main.ts;pkg-b/cond;-;0;unknown;Package exports condition is not observed: node;1
src/main.ts;pkg-b/cond;-;1;unknown;Package exports condition is not observed: node;1
src/main.ts;pkg-f;-;0;found;node_modules/pkg-f/f.js;1;0;0
src/main.ts;pkg-f;-;1;found;node_modules/pkg-f/f.js;1;0;0
src/main.ts;pkg-h;-;0;found;node_modules/pkg-h/h.js;1;0;0
src/main.ts;pkg-h;-;1;found;node_modules/pkg-h/h.js;1;0;0
src/main.ts;pkg-j/a;-;0;unknown;Package exports patterns are not observed: pkg-j/a;0
src/main.ts;pkg-j/a;-;1;unknown;Package exports patterns are not observed: pkg-j/a;0
src/main.ts;pkg-k;-;0;unknown;Package exports condition is not observed: weird;1
src/main.ts;pkg-k;-;1;unknown;Package exports condition is not observed: weird;1
src/main.ts;pkg-l;-;0;unknown;Package exports conditions are not observed: pkg-l;1
src/main.ts;pkg-l;-;1;unknown;Package exports conditions are not observed: pkg-l;1
src/main.ts;pkg-p;-;0;unknown;Package exports map shape is not observed: pkg-p;0
src/main.ts;pkg-p;-;1;unknown;Package exports map shape is not observed: pkg-p;0
src/main.ts;app;-;0;unknown;Package self-reference is not observed: app;0
src/main.ts;app;-;1;unknown;Package self-reference is not observed: app;0
src/main.ts;#internal;-;0;unknown;Package imports are not observed: #internal;0
src/main.ts;#internal;-;1;unknown;Package imports are not observed: #internal;0
src/main.ts;fs;-;0;missing
src/main.ts;fs;-;1;missing
src/main.ts;node:fs;-;0;missing
src/main.ts;node:fs;-;1;missing
src/main.ts;lodash;-;0;found;node_modules/@types/lodash/index.d.ts;1;0;0
src/main.ts;lodash;-;1;found;node_modules/@types/lodash/index.d.ts;1;0;0
src/main.ts;./util.js;esm;0;found;src/util.ts;0;0;0
src/main.ts;./util.js;esm;1;found;src/util.ts;0;0;0
src/main.ts;./esm.js;esm;0;missing
src/main.ts;./esm.js;esm;1;missing
src/main.ts;./dir;esm;0;missing
src/main.ts;./dir;esm;1;missing
src/main.ts;pkg-a;esm;0;found;node_modules/pkg-a/main.d.ts;1;0;0
src/main.ts;pkg-a;esm;1;found;node_modules/pkg-a/main.d.ts;1;0;0
src/main.ts;pkg-b;esm;0;found;node_modules/pkg-b/index.d.ts;1;0;0
src/main.ts;pkg-b;esm;1;found;node_modules/pkg-b/index.d.ts;1;0;0
src/main.ts;pkg-b/sub;esm;0;found;node_modules/pkg-b/sub.d.ts;1;0;0
src/main.ts;pkg-b/sub;esm;1;found;node_modules/pkg-b/sub.d.ts;1;0;0
src/main.ts;pkg-b/cond;esm;0;unknown;Package exports condition is not observed: node;1
src/main.ts;pkg-b/cond;esm;1;unknown;Package exports condition is not observed: node;1
src/main.ts;pkg-f;esm;0;found;node_modules/pkg-f/f.mjs;1;0;0
src/main.ts;pkg-f;esm;1;found;node_modules/pkg-f/f.mjs;1;0;0
src/main.ts;pkg-h;esm;0;found;node_modules/pkg-h/index.js;1;0;0
src/main.ts;pkg-h;esm;1;found;node_modules/pkg-h/index.js;1;0;0
src/main.ts;pkg-j/a;esm;0;unknown;Package exports patterns are not observed: pkg-j/a;0
src/main.ts;pkg-j/a;esm;1;unknown;Package exports patterns are not observed: pkg-j/a;0
src/main.ts;pkg-k;esm;0;unknown;Package exports condition is not observed: weird;1
src/main.ts;pkg-k;esm;1;unknown;Package exports condition is not observed: weird;1
src/main.ts;pkg-l;esm;0;found;node_modules/pkg-l/l.js;1;0;0
src/main.ts;pkg-l;esm;1;found;node_modules/pkg-l/l.js;1;0;0
src/main.ts;pkg-p;esm;0;unknown;Package exports map shape is not observed: pkg-p;0
src/main.ts;pkg-p;esm;1;unknown;Package exports map shape is not observed: pkg-p;0
src/main.ts;app;esm;0;unknown;Package self-reference is not observed: app;0
src/main.ts;app;esm;1;unknown;Package self-reference is not observed: app;0
src/main.ts;#internal;esm;0;unknown;Package imports are not observed: #internal;0
src/main.ts;#internal;esm;1;unknown;Package imports are not observed: #internal;0
src/main.ts;fs;esm;0;missing
src/main.ts;fs;esm;1;missing
src/main.ts;node:fs;esm;0;missing
src/main.ts;node:fs;esm;1;missing
src/main.ts;lodash;esm;0;missing
src/main.ts;lodash;esm;1;missing
src/main.ts;./util.js;cjs;0;found;src/util.ts;0;0;0
src/main.ts;./util.js;cjs;1;found;src/util.ts;0;0;0
src/main.ts;./esm.js;cjs;0;missing
src/main.ts;./esm.js;cjs;1;missing
src/main.ts;./dir;cjs;0;found;src/dir/index.ts;0;0;0
src/main.ts;./dir;cjs;1;found;src/dir/index.ts;0;0;0
src/main.ts;pkg-a;cjs;0;found;node_modules/pkg-a/main.d.ts;1;0;0
src/main.ts;pkg-a;cjs;1;found;node_modules/pkg-a/main.d.ts;1;0;0
src/main.ts;pkg-b;cjs;0;found;node_modules/pkg-b/index.d.ts;1;0;0
src/main.ts;pkg-b;cjs;1;found;node_modules/pkg-b/index.d.ts;1;0;0
src/main.ts;pkg-b/sub;cjs;0;found;node_modules/pkg-b/sub.d.ts;1;0;0
src/main.ts;pkg-b/sub;cjs;1;found;node_modules/pkg-b/sub.d.ts;1;0;0
src/main.ts;pkg-b/cond;cjs;0;unknown;Package exports condition is not observed: node;1
src/main.ts;pkg-b/cond;cjs;1;unknown;Package exports condition is not observed: node;1
src/main.ts;pkg-f;cjs;0;found;node_modules/pkg-f/f.js;1;0;0
src/main.ts;pkg-f;cjs;1;found;node_modules/pkg-f/f.js;1;0;0
src/main.ts;pkg-h;cjs;0;found;node_modules/pkg-h/h.js;1;0;0
src/main.ts;pkg-h;cjs;1;found;node_modules/pkg-h/h.js;1;0;0
src/main.ts;pkg-j/a;cjs;0;unknown;Package exports patterns are not observed: pkg-j/a;0
src/main.ts;pkg-j/a;cjs;1;unknown;Package exports patterns are not observed: pkg-j/a;0
src/main.ts;pkg-k;cjs;0;unknown;Package exports condition is not observed: weird;1
src/main.ts;pkg-k;cjs;1;unknown;Package exports condition is not observed: weird;1
src/main.ts;pkg-l;cjs;0;unknown;Package exports conditions are not observed: pkg-l;1
src/main.ts;pkg-l;cjs;1;unknown;Package exports conditions are not observed: pkg-l;1
src/main.ts;pkg-p;cjs;0;unknown;Package exports map shape is not observed: pkg-p;0
src/main.ts;pkg-p;cjs;1;unknown;Package exports map shape is not observed: pkg-p;0
src/main.ts;app;cjs;0;unknown;Package self-reference is not observed: app;0
src/main.ts;app;cjs;1;unknown;Package self-reference is not observed: app;0
src/main.ts;#internal;cjs;0;unknown;Package imports are not observed: #internal;0
src/main.ts;#internal;cjs;1;unknown;Package imports are not observed: #internal;0
src/main.ts;fs;cjs;0;missing
src/main.ts;fs;cjs;1;missing
src/main.ts;node:fs;cjs;0;missing
src/main.ts;node:fs;cjs;1;missing
src/main.ts;lodash;cjs;0;found;node_modules/@types/lodash/index.d.ts;1;0;0
src/main.ts;lodash;cjs;1;found;node_modules/@types/lodash/index.d.ts;1;0;0
format;src/main.ts;esm
format;src/esm.mts;esm
format;src/cjs.cts;cjs
format;src/pkgdir/lib/entry.ts;cjs
format;src/types.d.ts;esm
format;node_modules/pkg-h/h.js;esm
format;src/data.json;none
reads|node_modules/pkg-a/package.json,node_modules/pkg-b/package.json,node_modules/pkg-f/package.json,node_modules/pkg-h/package.json,node_modules/pkg-j/package.json,node_modules/pkg-k/package.json,node_modules/pkg-l/package.json,node_modules/pkg-p/package.json,package.json,src/pkgdir/package.json,tsconfig.json
problems|-
"#;

const BLOCKED: &str = r#"
config|{"compilerOptions":{"rootDirs":["a"]},"include":["src"]}
blocked|Compiler option is not observed: rootDirs
src/main.ts;./util;-;0;found;src/util.ts;0;0;0
src/main.ts;pkg-a;-;0;found;node_modules/pkg-a/main.d.ts;1;0;0
src/main.ts;fs;-;0;missing
reads|node_modules/pkg-a/package.json,tsconfig.json
problems|-
"#;

const PARTIAL: &str = r#"
config|{"compilerOptions":{"nope":1},"include":["src"]}
blocked|TSConfig settings are not fully observed
src/main.ts;./util;-;0;found;src/util.ts;0;0;0
src/main.ts;pkg-a;-;0;found;node_modules/pkg-a/main.d.ts;1;0;0
reads|node_modules/pkg-a/package.json,tsconfig.json
problems|Unknown compiler option 'nope'.
"#;

const CLASSIC: &str = r#"
config|{"compilerOptions":{"module":"es2015","moduleResolution":"classic"},"include":["src"]}
blocked|moduleResolution classic is not observed
src/main.ts;./util;-;0;found;src/util.ts;0;0;0
src/main.ts;pkg-a;-;0;found;node_modules/pkg-a/main.d.ts;1;0;0
reads|node_modules/pkg-a/package.json,tsconfig.json
problems|-
"#;

fn render(found: Lookup<Found>) -> String {
    match found {
        Lookup::Hit(found) => format!(
            "found;{};{};{};{}",
            found.path,
            u8::from(found.external),
            u8::from(found.directory_package),
            u8::from(found.via_paths)
        ),
        Lookup::Unknown(unknown) => {
            format!(
                "unknown;{};{}",
                unknown.reason,
                u8::from(unknown.package_internal)
            )
        }
        Lookup::Missing => "missing".to_owned(),
    }
}

fn render_format(found: Lookup<ModuleFormat>) -> String {
    match found {
        Lookup::Hit(ModuleFormat::Esm) => "esm".to_owned(),
        Lookup::Hit(ModuleFormat::Cjs) => "cjs".to_owned(),
        Lookup::Unknown(unknown) => format!("unknown;{}", unknown.reason),
        Lookup::Missing => "none".to_owned(),
    }
}

#[expect(
    clippy::cognitive_complexity,
    reason = "a table driver for the resolver cases: split it when the table moves (AD-327)"
)]
fn run(block: &str) {
    let mut config = "";
    let mut files: Vec<(&str, &str)> = TREE.to_vec();
    let lines: Vec<&str> = block.lines().filter(|line| !line.is_empty()).collect();
    for line in &lines {
        if let Some(text) = line.strip_prefix("config|") {
            config = text;
        }
    }
    files.push(("tsconfig.json", config));
    let tree = Tree::new(&files);
    let mut snapshot = Snapshot::new(&tree.path());
    let loaded = load_config(&mut snapshot, "tsconfig.json", &["src".to_owned()]);
    let mut resolver = Resolver::new(loaded.options, loaded.partial);
    for line in &lines {
        if let Some(reason) = line.strip_prefix("blocked|") {
            let got = resolver
                .blocked
                .as_ref()
                .map_or("-", |unknown| unknown.reason.as_str());
            assert_eq!(got, reason, "blocked");
        } else if let Some(expected) = line.strip_prefix("format;") {
            let (rel, format) = expected.split_once(';').expect("a format line");
            let got = render_format(resolver.format_of(&mut snapshot, rel));
            assert_eq!(got, format, "format of {rel}");
        } else if line.contains(';') {
            let parts: Vec<&str> = line.splitn(5, ';').collect();
            let mode = match parts[2] {
                "esm" => Some(ModuleFormat::Esm),
                "cjs" => Some(ModuleFormat::Cjs),
                _ => None,
            };
            let found = resolver.resolve(&mut snapshot, parts[1], parts[0], mode, parts[3] == "1");
            assert_eq!(
                render(found),
                parts[4],
                "{} imports {} ({})",
                parts[0],
                parts[1],
                parts[2]
            );
        }
    }
    for line in &lines {
        if let Some(expected) = line.strip_prefix("reads|") {
            let reads: Vec<String> = snapshot
                .inputs()
                .into_iter()
                .map(|input| input.path)
                .collect();
            assert_eq!(reads.join(","), expected, "inputs");
        } else if let Some(expected) = line.strip_prefix("problems|") {
            let problems: Vec<&str> = snapshot.problems.iter().map(String::as_str).collect();
            assert_eq!(
                if problems.is_empty() {
                    "-".to_owned()
                } else {
                    problems.join(";")
                },
                expected
            );
        }
    }
}

#[test]
fn node10_resolution_matches_the_python_resolver() {
    run(NODE10);
}

#[test]
fn bundler_resolution_matches_the_python_resolver() {
    run(BUNDLER);
}

#[test]
fn nodenext_resolution_and_formats_match_the_python_resolver() {
    run(NODENEXT);
}

#[test]
fn unobserved_settings_block_the_resolver_with_their_reason() {
    for block in [BLOCKED, PARTIAL, CLASSIC] {
        run(block);
    }
}

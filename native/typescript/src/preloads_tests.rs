// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::options_reader::{has_preload_flag, option_names};
use super::{
    malformed_config, mode_of, names_of, node_options, patches_loader, quoted_list, reaches_module,
    yaml_list,
};
use crate::source_input::ModuleFormat;

#[test]
fn a_script_names_each_preload_flag() {
    let names = option_names(
        "node -r a --require b --require=c --import d --loader=e --experimental-loader f x.js",
    );
    assert_eq!(names, ["a", "b", "c", "d", "e", "f"]);
}

#[test]
fn command_preloads_keep_their_runtime_mode() {
    assert_eq!(
        mode_of(
            "package.json",
            r#"{"scripts":{"cjs":"node --require hook a.js","esm":"node --import other a.js"}}"#,
            "hook"
        ),
        Some(ModuleFormat::Cjs)
    );
    assert_eq!(
        mode_of(
            "package.json",
            r#"{"scripts":{"esm":"node --import=hook a.js"}}"#,
            "hook"
        ),
        Some(ModuleFormat::Esm)
    );
    assert_eq!(
        mode_of("vitest.config.ts", "setupFiles:['hook']", "hook"),
        None
    );
}

#[test]
fn a_malformed_json_config_is_not_silent() {
    for name in ["package.json", "jest.config.json", ".mocharc.json"] {
        assert!(malformed_config(name, "{\"scripts\":"));
        assert!(!malformed_config(name, "{}"));
    }
    assert!(!malformed_config(".env", "NODE_OPTIONS=--require preload"));
}

#[test]
fn an_unreadable_dynamic_preload_target_is_named_as_a_gap() {
    assert!(has_preload_flag("node -r${PRELOAD} src/a.js"));
    assert_eq!(
        names_of(
            "package.json",
            r#"{"scripts":{"test":"node -r${PRELOAD} a.js"}}"#
        ),
        ["<dynamic preload target>"]
    );
    assert_eq!(
        names_of(
            "vitest.config.ts",
            "export default { test: { setupFiles: load() } }"
        ),
        ["<dynamic setupFiles target>"]
    );
    assert_eq!(
        names_of(
            "vitest.config.ts",
            "export default { test: { setupFiles: ['safe', getPreload()] } }"
        ),
        ["safe", "<dynamic setupFiles target>"]
    );
    assert_eq!(
        names_of(
            "vitest.config.ts",
            "export default { test: { projects: [{ setupFiles: ['safe'] }, { setupFiles: [getPreload()] }] } }"
        ),
        ["safe", "<dynamic setupFiles target>"]
    );
}

#[test]
fn node_options_in_a_script_is_read() {
    assert_eq!(
        option_names("NODE_OPTIONS='--require pre' node a.js"),
        ["pre"]
    );
    assert_eq!(
        option_names("cross-env NODE_OPTIONS=--import=pre node a.js"),
        ["pre"]
    );
    assert!(option_names("node --inspect a.js").is_empty());
}

#[test]
fn an_npmrc_or_env_line_sets_node_options() {
    assert_eq!(
        node_options("node-options=\"--require pre\"").as_deref(),
        Some("\"--require pre\"")
    );
    assert_eq!(
        node_options("export NODE_OPTIONS=-r pre").as_deref(),
        Some("-r pre")
    );
    assert_eq!(node_options("OTHER=1"), None);
    assert_eq!(
        names_of(".env.local", "NODE_OPTIONS=--require pre\n"),
        ["pre"]
    );
}

#[test]
fn the_jest_and_mocha_keys_of_package_json_are_read() {
    let text = r#"{"jest":{"setupFiles":["a"],"setupFilesAfterEnv":["b"],"globalSetup":"c"},
                  "mocha":{"require":["d"]},"scripts":{"test":"node -r e t.js"}}"#;
    let mut names = names_of("package.json", text);
    names.sort();
    assert_eq!(names, ["a", "b", "c", "d", "e"]);
}

#[test]
fn a_mocharc_yaml_and_a_vitest_config_are_read() {
    assert_eq!(
        yaml_list("require:\n  - a\n  - 'b'\nspec: x\n", "require"),
        ["a", "b"]
    );
    assert_eq!(yaml_list("require: c\n", "require"), ["c"]);
    let config = "export default { test: { setupFiles: ['./s.ts', \"pre\"], globals: true } }";
    assert_eq!(quoted_list(config, "setupFiles"), ["./s.ts", "pre"]);
}

#[test]
fn a_write_to_the_module_loader_is_a_patch() {
    for line in [
        "require.cache[k] = m;",
        "Module._load = f;",
        "M._resolveFilename = f;",
        "Module.prototype.require = f;",
        "delete Module._cache[k];",
    ] {
        assert!(patches_loader(line, true), "{line}");
    }
    for line in ["this._loadConfig();", "x.cacheSize = 1;", "require('a');"] {
        assert!(!patches_loader(line, true), "{line}");
    }
    // Without the module object, `this._cache` of another class is no patch.
    assert!(!patches_loader("this._cache = new Map();", false));
    assert!(patches_loader("require.cache[k] = m;", false));
}

#[test]
fn whitespace_and_newlines_do_not_hide_the_module_object() {
    for text in [
        "const Module = require ('module');",
        "const Module = require(\n  'module'\n);",
        "const Module = require ('node:module');",
    ] {
        assert!(reaches_module(text), "{text}");
    }
}

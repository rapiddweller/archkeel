// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: module resolution, which must read the settings as `config.load_config` does.
// Each expected value was printed by the Python function on the same TSConfig text.

use super::*;
use crate::config::load_config;
use crate::snapshot::Snapshot;
use crate::test_tree::Tree;

struct Case {
    name: &'static str,
    files: &'static [(&'static str, &'static str)],
    partial: bool,
    resolution: &'static str,
    resolve_json: bool,
    base_url: Option<&'static str>,
    paths: &'static [(&'static str, &'static [&'static str])],
    paths_base: &'static str,
    unmodeled: &'static [&'static str],
    problems: &'static [&'static str],
}

const CASES: &[Case] = &[
    Case {
        name: "bundler",
        files: &[("tsconfig.json", "{\"compilerOptions\":{\"moduleResolution\":\"bundler\",\"module\":\"esnext\",\"paths\":{\"@/*\":[\"src/*\"],\"z\":[\"z.ts\"]},\"baseUrl\":\".\"}}")],
        partial: false,
        resolution: "bundler",
        resolve_json: true,
        base_url: Some("."),
        paths: &[("@/*", &["src/*"]), ("z", &["z.ts"])],
        paths_base: ".",
        unmodeled: &[],
        problems: &[],
    },
    Case {
        name: "commonjs",
        files: &[("tsconfig.json", "{\"compilerOptions\":{\"module\":\"commonjs\",\"strict\":true}}")],
        partial: false,
        resolution: "node10",
        resolve_json: false,
        base_url: None,
        paths: &[],
        paths_base: ".",
        unmodeled: &[],
        problems: &[],
    },
    Case {
        name: "node16_pair",
        files: &[("tsconfig.json", "{\"compilerOptions\":{\"moduleResolution\":\"node16\"}}")],
        partial: true,
        resolution: "node16",
        resolve_json: false,
        base_url: None,
        paths: &[],
        paths_base: ".",
        unmodeled: &[],
        problems: &["Compiler option 5110: 'module' must be node16 with this moduleResolution."],
    },
    Case {
        name: "invalid",
        files: &[("tsconfig.json", "{\"compilerOptions\":{\"foo\":1,\"module\":\"nope\",\"allowJs\":\"yes\",\"baseUrl\":3,\"types\":\"x\",\"rootDirs\":[\"a\"],\"paths\":{\"a*b*\":[\"x\"],\"ok\":[1]}}}")],
        partial: true,
        resolution: "node10",
        resolve_json: false,
        base_url: None,
        paths: &[],
        paths_base: ".",
        unmodeled: &["rootDirs"],
        problems: &["Compiler option 5024: 'allowJs' must be a boolean.", "Compiler option 5024: 'baseUrl' must be a string.", "Compiler option 5024: 'types' must be a list of strings.", "Compiler option 5061: paths pattern 'a*b*' is not valid.", "Compiler option 5061: paths pattern 'ok' is not valid.", "Compiler option 6046: argument for 'module' is not valid.", "Unknown compiler option 'foo'."],
    },
    Case {
        name: "extends_missing",
        files: &[("tsconfig.json", "{\"extends\":\"./nope.json\",\"compilerOptions\":{\"module\":\"commonjs\"}}")],
        partial: true,
        resolution: "node10",
        resolve_json: false,
        base_url: None,
        paths: &[],
        paths_base: ".",
        unmodeled: &[],
        problems: &["File './nope.json' not found."],
    },
    Case {
        name: "config_dir",
        files: &[("tsconfig.json", "{\"compilerOptions\":{\"paths\":{\"@/*\":[\"${configDir}/src/*\"]}}}")],
        partial: false,
        resolution: "node10",
        resolve_json: false,
        base_url: None,
        paths: &[("@/*", &["${configDir}/src/*"])],
        paths_base: ".",
        unmodeled: &["paths with ${configDir}"],
        problems: &[],
    },
    Case {
        name: "script_env",
        files: &[("tsconfig.json", "{\"compilerOptions\":{\"noLib\":true,\"lib\":[\"es2020\"]},\"archkeel\":{\"scriptHost\":\"x\",\"scriptProviders\":[{\"source\":\"a\",\"provenance\":\"a\"},{\"source\":\"a\",\"provenance\":\"a\"},{\"source\":\"/a\",\"provenance\":\"b\"}]}}")],
        partial: true,
        resolution: "node10",
        resolve_json: false,
        base_url: None,
        paths: &[],
        paths_base: ".",
        unmodeled: &[],
        problems: &["Archkeel script host is not supported", "Archkeel script provider is declared more than once", "Archkeel script provider needs two snapshot-relative paths", "Compiler option 5053: 'lib' cannot be specified with 'noLib'."],
    },
    Case {
        name: "parent_base",
        files: &[("tsconfig.json", "{\"extends\":\"./configs/base.json\"}"), ("configs/base.json", "{\"compilerOptions\":{\"baseUrl\":\".\",\"paths\":{\"a\":[\"a.ts\"]},\"module\":\"nodenext\"}}")],
        partial: false,
        resolution: "nodenext",
        resolve_json: true,
        base_url: Some("configs"),
        paths: &[("a", &["a.ts"])],
        paths_base: "configs",
        unmodeled: &[],
        problems: &[],
    },
    Case {
        name: "target_only",
        files: &[("tsconfig.json", "{\"compilerOptions\":{\"target\":\"ES2020\",\"resolveJsonModule\":0,\"customConditions\":[],\"preserveSymlinks\":false,\"noDtsResolution\":0.0,\"resolvePackageJsonExports\":true}}")],
        partial: true,
        resolution: "classic",
        resolve_json: false,
        base_url: None,
        paths: &[],
        paths_base: ".",
        unmodeled: &["resolvePackageJsonExports"],
        problems: &["Compiler option 5024: 'noDtsResolution' must be a boolean.", "Compiler option 5024: 'resolveJsonModule' must be a boolean.", "Unknown compiler option 'noDtsResolution'."],
    },
    Case {
        name: "next_json",
        files: &[("tsconfig.json", "{\"compilerOptions\":{\"module\":\"NodeNext\",\"moduleResolution\":\"NodeNext\"}}")],
        partial: false,
        resolution: "nodenext",
        resolve_json: true,
        base_url: None,
        paths: &[],
        paths_base: ".",
        unmodeled: &[],
        problems: &[],
    },
    Case {
        name: "abs_include",
        files: &[("tsconfig.json", "{\"include\":[\"/abs\",\"src\"],\"compilerOptions\":{\"moduleResolution\":\"node\"}}")],
        partial: true,
        resolution: "node10",
        resolve_json: false,
        base_url: None,
        paths: &[],
        paths_base: ".",
        unmodeled: &[],
        problems: &[],
    },
    Case {
        name: "bad_options_type",
        files: &[("tsconfig.json", "{\"compilerOptions\":[1],\"include\":\"src\"}")],
        partial: true,
        resolution: "node10",
        resolve_json: false,
        base_url: None,
        paths: &[],
        paths_base: ".",
        unmodeled: &[],
        problems: &["Compiler option 5024: 'compilerOptions' must be an object.", "Compiler option 5024: 'include' must be a list of strings."],
    },
    Case {
        name: "node_resolution_alias",
        files: &[("tsconfig.json", "{\"compilerOptions\":{\"moduleResolution\":\"Node\",\"module\":\"es2022\"}}")],
        partial: false,
        resolution: "node10",
        resolve_json: false,
        base_url: None,
        paths: &[],
        paths_base: ".",
        unmodeled: &[],
        problems: &[],
    },
];

fn resolution_name(options: &Options) -> &'static str {
    match options.resolution() {
        Resolution::Node10 => "node10",
        Resolution::Classic => "classic",
        Resolution::Node16 => "node16",
        Resolution::NodeNext => "nodenext",
        Resolution::Bundler => "bundler",
    }
}

#[test]
fn settings_and_problems_match_the_python_reader() {
    for case in CASES {
        let mut files = case.files.to_vec();
        files.extend([("src/a.ts", "")]);
        let tree = Tree::new(&files);
        let mut snapshot = Snapshot::new(&tree.path());
        let config = load_config(&mut snapshot, "tsconfig.json", &["src".to_owned()]);
        let options = &config.options;
        assert_eq!(config.partial, case.partial, "{} partial", case.name);
        assert_eq!(resolution_name(options), case.resolution, "{}", case.name);
        assert_eq!(options.resolve_json(), case.resolve_json, "{}", case.name);
        assert_eq!(options.base_url.as_deref(), case.base_url, "{}", case.name);
        let paths: Vec<(&str, Vec<&str>)> = options
            .paths
            .iter()
            .map(|(pattern, targets)| {
                (
                    pattern.as_str(),
                    targets.iter().map(String::as_str).collect(),
                )
            })
            .collect();
        let expected: Vec<(&str, Vec<&str>)> = case
            .paths
            .iter()
            .map(|(pattern, targets)| (*pattern, targets.to_vec()))
            .collect();
        assert_eq!(paths, expected, "{} paths", case.name);
        assert_eq!(options.paths_base, case.paths_base, "{}", case.name);
        assert_eq!(options.unmodeled, case.unmodeled, "{}", case.name);
        let problems: Vec<&str> = snapshot.problems.iter().map(String::as_str).collect();
        assert_eq!(problems, case.problems, "{} problems", case.name);
    }
}

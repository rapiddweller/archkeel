// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The checks of `cli/config.py::parse_config` that decide a field of the request (AD-406).

use super::*;

fn parsed(text: &str) -> Result<Config, Refused> {
    parse(text.as_bytes(), "archkeel.toml")
}

const BASE: &str = "[scan]\nroots = [\"src\"]\nnamespace = \"app\"\ncontract = \"c.json\"\n";

fn typescript(extra: &str) -> Result<Config, Refused> {
    parsed(&format!("{BASE}language = \"typescript\"\n{extra}"))
}

#[test]
fn a_typescript_scan_gives_its_settings_with_the_python_defaults() {
    assert_eq!(
        typescript(""),
        Ok(Config {
            profile: archkeel_facts::envelope::Profile::TypeScript,
            roots: vec!["src".to_owned()],
            namespace: "app".to_owned(),
            contract: "c.json".to_owned(),
            tsconfig: "tsconfig.json".to_owned(),
            bundler: false,
            exclude_test_sources: false,
        })
    );
    let set = typescript(
        "tsconfig = \"./tsconfig.app.json\"\nbundler = true\nexclude_test_sources = true\n",
    )
    .unwrap();
    // `_path` keeps the tsconfig text; the roots and the contract take their POSIX form.
    assert_eq!(set.tsconfig, "./tsconfig.app.json");
    assert!(set.bundler && set.exclude_test_sources);
}

#[test]
fn roots_and_contract_take_the_form_of_pure_posix_path() {
    let text = "[scan]\nroots = [\"./src/\", \"lib//a\", \".\"]\nnamespace = \"a\"\n\
                contract = \"./x//c.json\"\nlanguage = \"typescript\"\n";
    // "." overlaps every other root.
    assert_eq!(
        parsed(text),
        Err(Refused::Invalid("scan.roots must not overlap".to_owned()))
    );
    let text = "[scan]\nroots = [\"./src/\", \"lib//a\"]\nnamespace = \"a\"\n\
                contract = \"./x//c.json\"\nlanguage = \"typescript\"\n";
    let config = parsed(text).unwrap();
    assert_eq!(config.roots, ["src", "lib/a"]);
    assert_eq!(config.contract, "x/c.json");
    assert_eq!(posix("."), ".");
}

#[test]
fn dart_and_a_configured_collector_are_unsupported_by_name() {
    for (language, profile) in [
        ("", Profile::Python),
        ("language = \"python\"\n", Profile::Python),
    ] {
        assert_eq!(
            parsed(&format!("{BASE}{language}")).unwrap().profile,
            profile
        );
    }
    let refused = parsed(&format!("{BASE}language = \"dart\"\n"));
    assert!(
        matches!(&refused, Err(Refused::Unsupported("profile", why)) if why.contains("dart")),
        "{refused:?}"
    );
    let refused = typescript("collector_argv = [\"/bin/x\"]\n");
    assert!(
        matches!(&refused, Err(Refused::Unsupported("collector", why)) if why.contains("/bin/x")),
        "{refused:?}"
    );
}

#[test]
fn a_rust_scan_needs_no_typescript_configuration() {
    let config = parsed(&format!(
        "{BASE}language = \"rust\"\nexclude_test_sources = true\n"
    ))
    .expect("the linked Rust collector can run this configuration");
    assert!(config.exclude_test_sources);
    assert_eq!(config.profile, archkeel_facts::envelope::Profile::Rust);
    let refused = parsed(&format!(
        "{BASE}language = \"rust\"\ncollector_argv = [\"/x\"]\n"
    ));
    assert!(matches!(refused, Err(Refused::Unsupported("collector", _))));
}

#[test]
fn an_invalid_configuration_is_refused_as_the_python_parser_refuses_it() {
    let cases = [
        ("[other]\n", "configuration must contain only [scan]"),
        ("[scan]\nroots = [\"src\"]\n", "[scan] requires roots"),
        ("unknown = 1\n", "[scan] requires roots"),
        ("language = \"go\"\n", "scan.language must be"),
        ("tsconfig = \"t.json\"\n", "scan.tsconfig is only valid"),
        ("bundler = true\n", "scan.bundler is only valid"),
    ];
    for (extra, message) in cases {
        let text = if extra.starts_with('[') {
            extra.to_owned()
        } else {
            format!("{BASE}{extra}")
        };
        let refused = parsed(&text);
        assert!(
            matches!(&refused, Err(Refused::Invalid(why)) if why.starts_with(message)),
            "{extra}: {refused:?}"
        );
    }
    let typed = [
        ("bundler = 1\n", "scan.bundler must be a boolean"),
        ("tsconfig = \".\"\n", "scan.tsconfig must be a safe POSIX"),
        (
            "tsconfig = \"../t.json\"\n",
            "scan.tsconfig must be a safe POSIX",
        ),
        (
            "tsconfig = \"/t.json\"\n",
            "scan.tsconfig must be a safe POSIX",
        ),
        (
            "tsconfig = \"t*.json\"\n",
            "scan.tsconfig must be a safe POSIX",
        ),
        (
            "exclude_test_sources = \"yes\"\n",
            "scan.exclude_test_sources",
        ),
        (
            "collector_timeout_seconds = 0\n",
            "scan.collector_timeout_seconds",
        ),
        (
            "collector_output_limit_bytes = true\n",
            "scan.collector_output_limit",
        ),
    ];
    for (extra, message) in typed {
        let refused = typescript(extra);
        assert!(
            matches!(&refused, Err(Refused::Invalid(why)) if why.starts_with(message)),
            "{extra}: {refused:?}"
        );
    }
}

#[test]
fn roots_namespace_and_contract_are_checked() {
    let scan = |roots: &str, namespace: &str, contract: &str| {
        parsed(&format!(
            "[scan]\nroots = {roots}\nnamespace = {namespace}\ncontract = {contract}\n\
             language = \"typescript\"\n"
        ))
    };
    let cases = [
        scan("[]", "\"a\"", "\"c\""),
        scan("[\"src\", \"src/\"]", "\"a\"", "\"c\""),
        scan("[\"src\", \"src/a\"]", "\"a\"", "\"c\""),
        scan("[\"a:b\"]", "\"a\"", "\"c\""),
        scan("[\"src\"]", "\"a-b\"", "\"c\""),
        scan("[\"src\"]", "\"1a\"", "\"c\""),
        scan("[\"src\"]", "\"a.\"", "\"c\""),
        scan("[\"src\"]", "\"a\"", "\".\""),
        scan("[\"src\"]", "\"a\"", "\"../c\""),
    ];
    for case in cases {
        assert!(matches!(case, Err(Refused::Invalid(_))), "{case:?}");
    }
    assert!(scan("[\"src\", \"srcx\"]", "\"a_b.c1\"", "\"c\"").is_ok());
}

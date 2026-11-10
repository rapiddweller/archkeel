// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the vendored libraries. The expected values are what the regular expressions of
// `resolve.Resolver.script_provider` accept (`tests/test_collector_native_script_deps.py` runs
// whole projects with a provider).

use super::*;

#[test]
fn lines_are_split_as_python_splits_them() {
    assert_eq!(
        split_lines("a\nb\r\nc\rd\u{2028}e"),
        ["a", "b", "c", "d", "e"]
    );
    assert_eq!(split_lines("a\n"), ["a"]);
    assert_eq!(split_lines("a\n\nb"), ["a", "", "b"]);
    assert!(split_lines("").is_empty());
}

#[test]
fn a_vendored_line_names_a_package_a_version_a_file_and_an_address() {
    let line = "Vendored from `vendor@1.2.3` (`dist/v.js`), https://example.org/vendor.";
    assert_eq!(vendored(line), Some(("vendor", "1.2.3")));
    let scoped = "Vendored from `@scope/pkg@1.0.0-rc.1+build.5` (`d.js`), https://e.org/p.";
    assert_eq!(vendored(scoped), Some(("@scope/pkg", "1.0.0-rc.1+build.5")));
    for bad in [
        "Vendored from `Vendor@1.2.3` (`d.js`), https://e.org/p.",
        "Vendored from `vendor@1.2` (`d.js`), https://e.org/p.",
        "Vendored from `vendor@1.2.3` (`d js`), https://e.org/p.",
        "Vendored from `vendor@1.2.3` (`d.js`), http://e.org/p.",
        "Vendored from `vendor@1.2.3` (`d.js`), https://e.org/p",
        "Vendored from `vendor@1.2.3` (`d.js`), https://.",
    ] {
        assert_eq!(vendored(bad), None, "{bad}");
    }
}

#[test]
fn the_digest_and_the_license_lines_have_one_form() {
    let digest = "a".repeat(64);
    assert_eq!(
        bundle_digest(&format!("Bundle SHA-256: `{digest}`.")),
        Some(digest.as_str())
    );
    assert_eq!(
        bundle_digest(&format!("Bundle SHA-256: `{}`.", "A".repeat(64))),
        None
    );
    assert_eq!(bundle_digest("Bundle SHA-256: `abc`."), None);
    assert!(is_license("SPDX license: `MIT`."));
    assert!(is_license("SPDX license: `(MIT OR Apache-2.0)`."));
    assert!(!is_license("SPDX license: ``."));
    assert!(!is_license("SPDX license: `MIT`"));
}

// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Inert-read and retained-door plants for the Python import survey.

use super::*;

#[test]
fn dill_settings_reads_keep_the_import_gap() {
    for source in [
        "import dill\nx = dill.settings['protocol']\n",
        "import dill as d\nx = d.settings['recurse']\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert!(
            found
                .iter()
                .any(|site| site.detail == "dill" && site.door.is_none()),
            "{source}"
        );
        assert!(
            !found.iter().any(|site| site.detail == "dill.settings"),
            "{source}"
        );
    }
    for source in [
        "import dill\ndill.settings = replacement\n",
        "import dill\ndef f(dill): return dill.settings\n",
        "import dill\ndill = replacement\nx = dill.settings\n",
        "import dill\nfrom elsewhere import *\nx = dill.settings\n",
        "import dill\nx = dill.settings.other\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert!(
            found.iter().any(|site| site.detail == "dill.settings"),
            "{source}"
        );
    }
}

#[test]
fn door_strings_with_unproved_equality_or_membership_keep_their_gap() {
    for source in [
        "result = value == '__import__'\n",
        "result = value in {'__import__'}\n",
        "names = {'__import__'}\nresult = value in names\n",
    ] {
        let tree = crate::test_tree(source, 12).expect("valid probe");
        let found = sites(
            &tree,
            Proof::default(),
            &Binders::of(&tree),
            &HashSet::new(),
        );
        assert!(
            found.iter().any(|site| site.detail == "__import__"),
            "{source}"
        );
    }
}

// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn a_compiler_refusal_never_reaches_the_tree_consumer() {
    for source in [
        "x = *a",
        "f(a=1, a=2)",
        "((a) := 1)",
        "try: pass\nexcept: pass\nexcept E: pass",
        "type X = (y := 1)",
    ] {
        assert!(
            crate::parse::parse(source, crate::test_minor(14)).is_err(),
            "{source}"
        );
    }
}

#[test]
fn every_new_input_loop_has_an_exact_work_charge() {
    for (source, expected) in [
        ("@decorator\ndef f(a=1, *, b=2):\n with a as x, b as y:\n  try: f(x, y, z=1, t=2)\n  except E: pass\n  except F as e: pass", 42),
        ("@decorator\nclass C[T: int = str, *Ts = *tuple[()]](Base, metaclass=Meta):\n def f(__x, y): pass", 29),
        ("'\\ud800'", 19),
        ("((a) := 1)", 4),
    ] {
        let module = crate::test_tree(source, 14).unwrap();
        let mut check = Check {
            source, minor: crate::test_minor(14), work: Work::new(), depth: 0,
            blocks: 0, star: false, star_annotation: None, restricted: false, private: None, reason: None,
        };
        check.docstring(&module.body);
        check.visit_body(&module.body);
        assert_eq!(check.work.used(), expected, "{source}");
    }
}

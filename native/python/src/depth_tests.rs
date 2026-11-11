// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The expected depths are the values of `source._ast_depth(ast.parse(text))` on CPython 3.12.

use ruff_python_parser::parse_module;

use super::depth;

fn levels(text: &str) -> usize {
    depth(parse_module(text).unwrap().syntax())
}

#[test]
fn a_context_or_an_operator_is_one_level() {
    assert_eq!(levels("x\n"), 4);
    assert_eq!(levels("1\n"), 3);
    assert_eq!(levels("a + b\n"), 5);
    assert_eq!(levels("a < b < c\n"), 5);
    assert_eq!(levels("a.b.c\n"), 6);
    assert_eq!(levels("x += 1\n"), 4);
}

#[test]
fn the_wrappers_of_ruff_add_no_level() {
    assert_eq!(levels("f(a, k=b)\n"), 6);
    assert_eq!(levels("@d\ndef f(a: int = 1): pass\n"), 6);
    assert_eq!(levels("'a' 'b'\n"), 3);
    assert_eq!(levels("f'{a!r:>{w}}'\n"), 8);
    assert_eq!(levels("lambda: 0\n"), 4);
    assert_eq!(levels("class C(B, metaclass=M): pass\n"), 5);
}

#[test]
fn each_elif_is_one_more_if() {
    let chain: String = "if a:\n pass\n".to_owned() + &"elif b:\n pass\n".repeat(10);
    assert_eq!(levels(&chain), 14);
    assert_eq!(levels("if a:\n pass\nelse:\n x\n"), 5);
}

#[test]
fn a_left_chain_of_200_000_operands_needs_no_recursion() {
    // The parser builds the chain in a loop; only the walk of this module could recurse.
    let levels = std::thread::Builder::new()
        .stack_size(256 * 1024 * 1024)
        .spawn(|| {
            let text = format!("x = {}\n", vec!["a"; 200_000].join("+"));
            let module = parse_module(&text).unwrap().into_syntax();
            let levels = depth(&module);
            // A deep tree drops by recursion, as in `parse::parse`.
            std::mem::forget(module);
            levels
        })
        .unwrap()
        .join()
        .unwrap();
    assert_eq!(levels, 200_003);
}

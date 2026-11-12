// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `_canonical_range` and `_source_tokens` of `analyzer/dart/parse.py`: the tokens of a byte
//! range, joined with the spacing rules of the Python collector. The token walk uses no
//! recursion; Python recurses once for each level of the tree.

use tree_sitter::Node;

use crate::pytext::{is_alnum, rstrip, strip};
use crate::tree::{Source, Work};

/// The `_Lexeme` groups that `_canonical_range` reads.
const CLOSERS: [&str; 3] = [")", "]", "}"];
const OPENERS: [&str; 3] = ["(", "[", "{"];
const ATTACHED: [&str; 10] = [")", "]", "}", ".", "?.", "?..", "..", "?[]", "!.", "?["];
const OPERATORS: [&str; 18] = [
    "=", "=>", "+", "-", "*", "/", "~/", "%", "??", "&&", "||", "==", "!=", "<", ">", "<=", ">=",
    "??=",
];
const COMMENTS: [&str; 2] = ["comment", "documentation_comment"];

/// `_canonical_range(root, source, start, end)`.
pub(crate) fn canonical_range<'t>(
    root: Node<'t>,
    source: &Source<'_>,
    work: &Work<'t>,
    start: usize,
    end: usize,
) -> String {
    let mut output = String::new();
    let mut previous_word = false;
    source_tokens(root, start, end, work, |token, in_type_arguments| {
        let value = source.text(token);
        // The output copies each token: a long string literal costs its length.
        work.charge(value.len());
        previous_word = join(&mut output, &value, previous_word, in_type_arguments);
    });
    strip(&output).to_owned()
}

/// One step of the loop of `_canonical_range`: append `value` and give the new `previous_word`.
fn join(output: &mut String, value: &str, previous_word: bool, in_type_arguments: bool) -> bool {
    if value == "," {
        truncate_space(output);
        output.push_str(", ");
        return false;
    }
    if ATTACHED.contains(&value) {
        truncate_space(output);
        let closes_group = CLOSERS.contains(&value);
        // `prefix = output[:-1].rstrip()` is the text before `value`, which has one character
        // when it closes a group, and Python reads `prefix` only then.
        if closes_group && output.ends_with(',') {
            output.pop();
            truncate_space(output);
        }
        output.push_str(value);
        return closes_group;
    }
    if OPENERS.contains(&value) {
        truncate_space(output);
        output.push_str(value);
        return false;
    }
    if OPERATORS.contains(&value) {
        truncate_space(output);
        if matches!(value, "<" | ">") && in_type_arguments {
            output.push_str(value);
            return value == ">";
        }
        output.push(' ');
        output.push_str(value);
        output.push(' ');
        return false;
    }
    let word = value
        .chars()
        .next()
        .is_some_and(|first| is_alnum(first) || matches!(first, '_' | '$' | '"' | '\''));
    if previous_word && word {
        output.push(' ');
    }
    output.push_str(value);
    word
}

/// `output = output.rstrip()` in place.
fn truncate_space(output: &mut String) {
    let kept = rstrip(output).len();
    output.truncate(kept);
}

/// `_source_tokens(root, start, end)`: each leaf and each string literal that overlaps the range,
/// in document order, without comments. `emit` also gets whether a `type_arguments` node is an
/// ancestor of the token, the test that `_canonical_range` makes with `_ancestors`.
fn source_tokens<'t>(
    root: Node<'t>,
    start: usize,
    end: usize,
    work: &Work<'t>,
    mut emit: impl FnMut(Node<'t>, bool),
) {
    let mut cursor = root.walk();
    // For each ancestor of the cursor node: the count of `type_arguments` nodes up to it.
    let mut path: Vec<usize> = Vec::new();
    loop {
        let node = cursor.node();
        work.charge(1);
        let overlaps = node.end_byte() > start && node.start_byte() < end;
        let mut descend = false;
        if overlaps && !COMMENTS.contains(&node.kind()) {
            let in_type_arguments = path.last().is_some_and(|count| *count > 0);
            if node.kind() == "string_literal" || node.child_count() == 0 {
                emit(node, in_type_arguments);
            } else {
                descend = true;
            }
        }
        // The children that end at or before `start` give no token: skip them in one step.
        if descend && cursor.goto_first_child_for_byte(start).is_some() {
            let count = path.last().copied().unwrap_or(0);
            path.push(count.saturating_add(usize::from(node.kind() == "type_arguments")));
            if cursor.node().start_byte() < end {
                continue;
            }
        } else if path.is_empty() {
            return;
        } else if cursor.goto_next_sibling() && cursor.node().start_byte() < end {
            continue;
        }
        // The loop of the children breaks at the first child that starts at `end` or later.
        loop {
            if !cursor.goto_parent() {
                return;
            }
            path.pop();
            if path.is_empty() {
                return;
            }
            if cursor.goto_next_sibling() && cursor.node().start_byte() < end {
                break;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::join;

    fn joined(tokens: &[&str]) -> String {
        let mut output = String::new();
        let mut previous = false;
        for token in tokens {
            previous = join(&mut output, token, previous, false);
        }
        crate::pytext::strip(&output).to_owned()
    }

    #[test]
    fn a_comma_before_a_closer_goes() {
        assert_eq!(joined(&["f", "(", "a", ",", ")"]), "f(a)");
        assert_eq!(joined(&["[", "a", ",", "b", ",", "]"]), "[a, b]");
    }

    #[test]
    fn words_get_one_space_and_operators_two() {
        assert_eq!(
            joined(&["new", "A", "(", "x", "+", "1", ")"]),
            "new A(x + 1)"
        );
        assert_eq!(joined(&["a", "?.", "b", "..", "c"]), "a?.b..c");
        assert_eq!(joined(&["'s'", "x"]), "'s' x");
        assert_eq!(joined(&["_a", "$b"]), "_a $b");
    }

    #[test]
    fn a_closer_is_a_word_end_and_an_empty_token_is_not() {
        assert_eq!(joined(&["f", "(", ")", "x"]), "f() x");
        assert_eq!(joined(&["a", "", "b"]), "ab");
    }
}

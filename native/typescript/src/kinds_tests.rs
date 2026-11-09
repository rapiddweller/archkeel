// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: every reader of a node kind. A kind text that the grammar does not know would never
// match, so a typo in `NAMES` must fail here.

use tree_sitter::Language;
use tree_sitter_typescript::{LANGUAGE_TSX, LANGUAGE_TYPESCRIPT};

use super::*;

fn grammar_texts(language: &Language) -> Vec<&'static str> {
    (0..language.node_kind_count() as u16)
        .filter_map(|id| language.node_kind_for_id(id))
        .collect()
}

/// The texts of `_NodeKind` that no grammar of the TypeScript collector has: the Python enum
/// lists them, but `tree-sitter-typescript` 0.23.2 never produces them as a kind.
const NOT_IN_THE_GRAMMAR: [&str; 2] = ["class_expression", "rest_parameter"];

#[test]
fn every_kind_text_exists_in_a_grammar() {
    let typescript = grammar_texts(&LANGUAGE_TYPESCRIPT.into());
    let tsx = grammar_texts(&LANGUAGE_TSX.into());
    let missing: Vec<&str> = NAMES
        .iter()
        .map(|(text, _)| *text)
        .filter(|text| !typescript.contains(text) && !tsx.contains(text))
        .collect();
    assert_eq!(missing, NOT_IN_THE_GRAMMAR);
}

#[test]
fn a_kind_text_names_one_kind() {
    let mut texts: Vec<&str> = NAMES.iter().map(|(text, _)| *text).collect();
    texts.sort_unstable();
    texts.dedup();
    assert_eq!(texts.len(), NAMES.len());
}

#[test]
fn a_named_kind_and_a_token_of_the_same_text_are_one_kind() {
    let language: Language = LANGUAGE_TYPESCRIPT.into();
    let map = KindMap::new(&language);
    // `module` is a node (`module X {}`) and a keyword; `type` is a keyword.
    let ids: Vec<u16> = (0..language.node_kind_count() as u16)
        .filter(|id| language.node_kind_for_id(*id) == Some("module"))
        .collect();
    assert!(ids.len() >= 2, "{ids:?}");
    for id in ids {
        assert_eq!(map.table[usize::from(id)].0, K::Module);
    }
    let unknown = (0..language.node_kind_count() as u16)
        .find(|id| language.node_kind_for_id(*id) == Some("jsx_element"));
    // The grammar without JSX does not know the kind; a kind outside `NAMES` is `K::Other`.
    assert!(unknown.is_none());
    let other = (0..language.node_kind_count() as u16)
        .find(|id| language.node_kind_for_id(*id) == Some("regex"))
        .map(|id| map.table[usize::from(id)].0);
    assert_eq!(other, Some(K::Other));
}

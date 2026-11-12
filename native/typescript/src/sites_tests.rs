// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the walk. The expected lines are printed by `parse.parse()` of the Python collector for
// each source (`tests/test_collector_native_syntax.py` compares every fact on real trees).

use super::{SiteKind, SiteUse};
use crate::parse::parse;
use crate::site_syntax::ReceiverKind;
use crate::syntax::Parsers;
use crate::walk::Syntax;

#[test]
fn site_kind_names_are_stable() {
    assert_eq!(SiteKind::Call.as_str(), "call");
    assert_eq!(SiteKind::New.as_str(), "new");
    assert_eq!(SiteKind::Reference.as_str(), "reference");
}

fn facts(rel: &str, source: &str) -> Syntax {
    parse(&mut Parsers::new(), rel, source.as_bytes()).syntax
}

/// One line for each site: kind, expression, scope, name, receiver, path, free, escape, shadowed,
/// ambiguous.
fn lines(rel: &str, source: &str) -> Vec<String> {
    let syntax = facts(rel, source);
    let data = source.as_bytes();
    let sites = &syntax.sites;
    sites
        .sites
        .iter()
        .map(|site| {
            let text = |item: Option<crate::site_paths::Text>| {
                item.map_or_else(|| "None".to_owned(), |text| text.decode(data))
            };
            let scope = site
                .scope
                .map_or_else(|| "None".to_owned(), |at| syntax.scopes.qualified(at));
            let path = site
                .path
                .map(|path| sites.paths.names(path, data).join("."))
                .unwrap_or_default();
            let kind = match site.kind {
                SiteKind::Call => "call",
                SiteKind::New => "new",
                SiteKind::Reference => "reference",
            };
            format!(
                "{kind} {} scope={scope} name={} receiver={} path=[{path}] free={} escape={} \
                 shadow={:?} ambiguous={}",
                match site.expression {
                    crate::sites::Expression::Node(node) => node.decode(data),
                    crate::sites::Expression::Member(receiver, name) =>
                        format!("{}.{}", receiver.decode(data), name.decode(data)),
                },
                text(site.name),
                text(site.receiver),
                site.script_free,
                site.script_escape,
                sites.names.shadowed(site.shadow.chain, data),
                site.scope_ambiguous,
            )
        })
        .collect()
}

#[test]
fn a_call_a_member_call_and_the_references_of_a_method_equal_python() {
    let found = lines(
        "a.ts",
        "class K { m(p) { const r = f.a.b(1); if (p === 'x') { g(p); } } }\nfoo(bar);\nnew Baz(x);",
    );
    let expected = [
        "call f.a.b scope=K.m name=b receiver=f.a path=[f.a.b] free=true escape=false shadow=[\"p\", \"r\"] ambiguous=false",
        "reference p scope=K.m name=p receiver=None path=[p] free=false escape=true shadow=[\"p\", \"r\"] ambiguous=false",
        "call g scope=K.m name=g receiver=None path=[g] free=true escape=false shadow=[\"p\", \"r\"] ambiguous=true",
        "reference p scope=K.m name=p receiver=None path=[p] free=false escape=true shadow=[\"p\", \"r\"] ambiguous=true",
        "call foo scope=None name=foo receiver=None path=[foo] free=true escape=false shadow=[] ambiguous=false",
        "reference bar scope=None name=bar receiver=None path=[bar] free=true escape=true shadow=[] ambiguous=false",
        "new Baz scope=None name=Baz receiver=None path=[Baz] free=true escape=false shadow=[] ambiguous=false",
        "reference x scope=None name=x receiver=None path=[x] free=true escape=true shadow=[] ambiguous=false",
    ];
    assert_eq!(found, expected);
}

#[test]
fn a_script_wrapper_keeps_its_scope_certain_and_a_with_blocks_every_name() {
    let found = lines(
        "a.js",
        "(function(window){ var z = window.foo; z(1); })(window);\nwith (o) { q(1); }",
    );
    // The call of the wrapper itself has no static path; `window` inside is bound by the wrapper.
    assert!(found[0].starts_with("call (function(window){"));
    assert!(found[0].contains("free=false"));
    assert!(found[1].ends_with("shadow=[\"window\", \"z\"] ambiguous=false"));
    assert!(found[4].starts_with("reference window ") && found[4].contains("free=true"));
    assert!(found[6].starts_with("call q ") && found[6].contains("free=false"));
}

#[test]
fn a_type_use_and_a_computed_receiver_equal_python() {
    let found = lines(
        "a.ts",
        "const f = () => { let loc = 1; return a[loc].b; };\nfunction h(x: T) { return x as Foo; }",
    );
    assert!(found[0].starts_with("reference a scope=None") && found[0].contains("ambiguous=true"));
    assert!(found[2].starts_with("reference a[loc].b ") && found[2].contains("path=[]"));
    assert!(found[3].starts_with("reference T scope=h") && found[3].contains("free=false"));
    let syntax = facts("a.ts", "function h(x: T) { return x as Foo; }");
    let uses: Vec<SiteUse> = syntax.sites.sites.iter().map(|site| site.usage).collect();
    assert_eq!(uses, [SiteUse::Type, SiteUse::Value, SiteUse::Type]);
    let kinds: Vec<ReceiverKind> = syntax
        .sites
        .sites
        .iter()
        .map(|site| site.receiver_kind)
        .collect();
    assert_eq!(kinds, [ReceiverKind::None; 3]);
}

#[test]
fn a_string_comparison_names_its_scope_and_ignores_a_repair() {
    let syntax = facts(
        "a.ts",
        "function f(k) { if (k === 'a' || ('b') != k) {} switch (k) { case 'c': } }\nk == 'ok' ==",
    );
    let found: Vec<(String, Option<String>)> = syntax
        .sites
        .comparisons
        .iter()
        .map(|item| {
            (
                item.span.excerpt.clone(),
                item.scope.map(|at| syntax.scopes.qualified(at)),
            )
        })
        .collect();
    assert_eq!(
        found,
        [
            ("'a'".to_owned(), Some("f".to_owned())),
            ("'b'".to_owned(), Some("f".to_owned())),
            ("'c'".to_owned(), Some("f".to_owned())),
        ]
    );
}

#[test]
fn a_write_to_a_published_global_is_no_free_name() {
    let found = lines("a.js", "window.x = y;\nwindow.z;");
    // Sorted by position: `window`, `window.x`, `y`, `window`, `window.z`.
    assert!(found[0].starts_with("reference window ") && found[0].contains("free=false"));
    assert!(found[1].starts_with("reference window.x ") && found[1].contains("free=false"));
    assert!(found[2].starts_with("reference y ") && found[2].contains("free=true"));
    assert!(found[4].starts_with("reference window.z ") && found[4].contains("free=true"));
}

#[test]
fn the_receiver_of_a_member_call_is_this_other_or_none() {
    let syntax = facts(
        "a.ts",
        "class K { m() { this.y(); a.b(); f(); (g()).h(); } }",
    );
    let found: Vec<(SiteKind, ReceiverKind)> = syntax
        .sites
        .sites
        .iter()
        .filter(|site| site.kind == SiteKind::Call)
        .map(|site| (site.kind, site.receiver_kind))
        .collect();
    assert_eq!(
        found,
        [
            (SiteKind::Call, ReceiverKind::This),
            (SiteKind::Call, ReceiverKind::Other),
            (SiteKind::Call, ReceiverKind::None),
            (SiteKind::Call, ReceiverKind::Other),
            (SiteKind::Call, ReceiverKind::None),
        ]
    );
}

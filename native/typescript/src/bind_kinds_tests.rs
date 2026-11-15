// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the walk and the script tree. A name that TypeScript binds at run time (an `enum`, a
// `namespace` with a value, the `arguments` of a function) is no read of a script global; a
// name that it does not bind stays one. Each plant states the truth as `free`: whether the site
// reads a global.

use crate::parse::parse;
use crate::syntax::Parsers;

/// For each site of `source` that has a path: `path=free`.
fn sites(rel: &str, source: &str) -> Vec<String> {
    let syntax = parse(&mut Parsers::new(), rel, source.as_bytes()).syntax;
    let data = source.as_bytes();
    let sites = &syntax.sites;
    sites
        .sites
        .iter()
        .filter_map(|site| {
            let path = site.path?;
            Some(format!(
                "{}={}",
                sites.paths.names(path, data).join("."),
                site.script_free
            ))
        })
        .collect()
}

/// Whether the one read `K.A` of the source reads a global.
fn free(source: &str, path: &str) -> bool {
    let found = sites("a.ts", source);
    let wanted = format!("{path}=");
    let hits: Vec<&String> = found.iter().filter(|s| s.starts_with(&wanted)).collect();
    assert!(!hits.is_empty(), "no site {path} in {found:?}");
    hits.iter().all(|hit| hit.ends_with("=true"))
}

#[test]
fn a_local_enum_is_a_binding() {
    assert!(!free(
        "enum K { A }\nexport function f() { return K.A; }",
        "K.A"
    ));
    assert!(!free(
        "export enum K { A }\nexport function f() { return K.A; }",
        "K.A"
    ));
    assert!(!free(
        "const enum K { A }\nexport function f() { return K.A; }",
        "K.A"
    ));
    assert!(!free(
        "export const enum K { A }\nexport const x = K.A;",
        "K.A"
    ));
}

#[test]
fn an_enum_with_the_name_of_a_standard_global_shadows_it() {
    assert!(!free(
        "enum Error { A }\nexport const x = Error.A;",
        "Error.A"
    ));
}

#[test]
fn a_namespace_with_a_value_is_a_binding() {
    assert!(!free(
        "namespace N { export const a = 1; }\nexport const x = N.a;",
        "N.a"
    ));
    assert!(!free(
        "namespace N { export function f() {} }\nexport const x = N.f();",
        "N.f"
    ));
    assert!(!free(
        "namespace N { export class C {} }\nexport const x = new N.C();",
        "N.C"
    ));
    assert!(!free(
        "namespace N { export enum E { A } }\nexport const x = N.E.A;",
        "N.E.A"
    ));
    assert!(!free(
        "module N { export const a = 1; }\nexport const x = N.a;",
        "N.a"
    ));
}

#[test]
fn a_nested_namespace_name_binds_its_first_name_when_the_inner_one_has_a_value() {
    assert!(!free(
        "namespace A.B { export const x = 1; }\nexport const y = A.B.x;",
        "A.B.x"
    ));
    assert!(!free(
        "namespace A { export namespace B { export const x = 1; } }\nexport const y = A.B.x;",
        "A.B.x"
    ));
}

#[test]
fn a_type_only_namespace_is_no_binding() {
    assert!(free(
        "namespace N { export interface I {} }\nexport const x = N.y;",
        "N.y"
    ));
    assert!(free(
        "namespace N { export type T = number; }\nexport const x = N.y;",
        "N.y"
    ));
    assert!(free(
        "namespace N { export namespace M { export type T = 1; } }\nexport const x = N.y;",
        "N.y"
    ));
    assert!(free(
        "namespace N { export const enum E { A } }\nexport const x = N.y;",
        "N.y"
    ));
    assert!(free("namespace N {}\nexport const x = N.y;", "N.y"));
}

#[test]
fn an_ambient_enum_or_namespace_binds_nothing() {
    assert!(free("declare enum K { A }\nexport const x = K.A;", "K.A"));
    assert!(free(
        "declare const enum K { A }\nexport const x = K.A;",
        "K.A"
    ));
    assert!(free(
        "declare namespace N { const a: number; }\nexport const x = N.a;",
        "N.a"
    ));
    assert!(free(
        "declare namespace N { enum E { A } }\nexport const x = N.E;",
        "N.E"
    ));
}

#[test]
fn an_enum_and_a_namespace_of_one_name_merge() {
    let merged = "enum E { A }\nnamespace E { export function f() {} }\nexport const x = E.f();";
    assert!(!free(merged, "E.f"));
    let type_only = "enum E { A }\nnamespace E { export type T = 1; }\nexport const x = E.A;";
    assert!(!free(type_only, "E.A"));
}

#[test]
fn an_enum_binds_in_its_own_scope_only() {
    let block = "if (c) { enum K { A } }\nexport const x = K.A;";
    assert!(free(block, "K.A"));
    let function = "export function f() { enum K { A } return K.A; }\nexport const x = K.A;";
    let found: Vec<String> = sites("a.ts", function)
        .into_iter()
        .filter(|site| site.starts_with("K.A="))
        .collect();
    assert_eq!(
        found,
        ["K.A=false", "K.A=true"],
        "bound inside, free outside"
    );
}

#[test]
fn arguments_binds_in_a_function_that_is_no_arrow() {
    assert!(!free(
        "export function f() { return arguments[0]; }",
        "arguments"
    ));
    assert!(!free(
        "export const f = function () { return arguments.length; };",
        "arguments"
    ));
    assert!(!free(
        "export function* g() { yield arguments[0]; }",
        "arguments"
    ));
    assert!(!free(
        "export class C { m() { return arguments[0]; } }",
        "arguments"
    ));
    assert!(!free(
        "export const o = { get m() { return arguments.length; } };",
        "arguments"
    ));
}

#[test]
fn an_arrow_function_takes_the_arguments_of_the_function_around_it() {
    let inside = "export function f() { return () => arguments[0]; }";
    assert!(!free(inside, "arguments"));
    let top = "export const f = () => arguments[0];";
    assert!(free(top, "arguments"));
}

#[test]
fn arguments_at_the_top_of_a_module_is_free() {
    assert!(free("export const x = arguments[0];", "arguments"));
    assert!(free("export const x = arguments;", "arguments"));
}

#[test]
fn a_parameter_or_a_local_named_arguments_is_unchanged() {
    assert!(!free(
        "export function f(arguments) { return arguments[0]; }",
        "arguments"
    ));
    assert!(!free(
        "export function f() { var arguments = []; return arguments[0]; }",
        "arguments"
    ));
}

#[test]
fn a_function_of_a_class_field_does_not_leak_arguments_to_the_outside() {
    assert!(free(
        "export function f() { return 1; }\nexport const x = arguments[0];",
        "arguments"
    ));
}

#[test]
fn a_shadowing_inner_scope_still_wins() {
    let inner = "enum K { A }\nexport function f(K: { A: number }) { return K.A; }";
    assert!(!free(inner, "K.A"));
}

/// The write paths of a file, for the script tree.
fn paths(rel: &str, source: &str) -> Vec<Vec<String>> {
    parse(&mut Parsers::new(), rel, source.as_bytes())
        .syntax
        .script
        .write_paths
}

#[test]
fn a_write_through_a_bound_name_is_no_write_through_a_global() {
    // The member `B` stays a named write of any object (AD-460); the head is no global.
    let enum_write = paths("a.ts", "export enum Error { A }\nError.B = 1;\n");
    assert_eq!(enum_write, [["B"]]);
    let value = "export namespace N { export const a = 1; }\nN.b = 1;\n";
    assert_eq!(paths("a.ts", value), [["b"]]);
    let arguments = "export function f() { arguments.x = 1; }\n";
    assert_eq!(paths("a.ts", arguments), [["x"]]);
}

#[test]
fn a_write_through_a_name_that_nothing_binds_stays_a_write_through_a_global() {
    let ambient = paths("a.ts", "declare enum Error { A }\nError.B = 1;\n");
    assert!(ambient.contains(&vec!["Error".to_owned(), "B".to_owned()]));
    let types = "export namespace N { export type T = 1; }\nN.b = 1;\n";
    assert!(paths("a.ts", types).contains(&vec!["N".to_owned(), "b".to_owned()]));
    let arrow = "export const f = () => { arguments.x = 1; };\n";
    assert!(paths("a.ts", arrow).contains(&vec!["arguments".to_owned(), "x".to_owned()]));
}

#[test]
fn a_namespace_nested_deeper_than_the_limit_binds_nothing() {
    let near = "namespace A { namespace B { namespace C { export const x = 1; } } }\nexport const y = A.B;";
    assert!(!free(near, "A.B"));
    let mut deep = String::from("export const x = 1;");
    for name in ["Z", "Y", "X", "W", "V", "U", "T", "S", "R", "Q"] {
        deep = format!("namespace {name} {{ {deep} }}");
    }
    assert!(free(&format!("{deep}\nexport const y = Z.Y;"), "Z.Y"));
}

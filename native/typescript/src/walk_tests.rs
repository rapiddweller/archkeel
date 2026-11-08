// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the syntax walk. The expected lines are printed by `parse.parse()` of the Python
// collector for each source. `summary` writes the same lines from the native facts, so a difference
// shows as one line of text.

use crate::definitions::DefinitionKind;
use crate::members::Visibility;
use crate::parse::parse;
use crate::syntax::Parsers;
use crate::walk::Syntax;

fn word<T: std::fmt::Display>(value: Option<T>) -> String {
    value.map_or_else(|| "None".to_owned(), |item| item.to_string())
}

fn kind(item: DefinitionKind) -> &'static str {
    match item {
        DefinitionKind::Class => "class",
        DefinitionKind::Interface => "interface",
        DefinitionKind::Enum => "enum",
        DefinitionKind::Method => "method",
        DefinitionKind::Function => "function",
        DefinitionKind::TypeAlias => "type_alias",
        DefinitionKind::Constant => "constant",
    }
}

fn visibility(item: Option<Visibility>) -> &'static str {
    match item {
        Some(Visibility::Public) => "public",
        Some(Visibility::Protected) => "protected",
        Some(Visibility::Private) => "private",
        None => "None",
    }
}

fn flag(value: bool) -> &'static str {
    if value {
        "True"
    } else {
        "False"
    }
}

fn at(span: &crate::syntax::Span) -> String {
    format!("{}:{}", span.line, span.column)
}

fn summary(syntax: &Syntax) -> Vec<String> {
    let mut out = Vec::new();
    for d in &syntax.definitions {
        let members: Vec<String> = d
            .members
            .iter()
            .map(|m| {
                format!(
                    "{}:{}:{}:{}:{}:{}",
                    m.name,
                    word(m.annotation.as_ref()),
                    visibility(m.visibility),
                    flag(m.is_static),
                    word(m.literal.as_ref()),
                    m.decorator_sources.len()
                )
            })
            .collect();
        let bases: Vec<String> = d
            .bases
            .iter()
            .map(|b| {
                format!(
                    "{}:{}",
                    b.name,
                    if b.realizes { "realizes" } else { "inherits" }
                )
            })
            .collect();
        let params: Vec<String> = d
            .parameters
            .iter()
            .map(|p| {
                format!(
                    "{}:{}:{}:{}:{}",
                    p.name,
                    word(p.annotation.as_ref()),
                    flag(p.optional),
                    flag(p.rest),
                    word(p.default.as_ref())
                )
            })
            .collect();
        out.push(format!(
            "D {} {} {} {} ex={} vis={} top={} st={} ab={} as={} dec={} mc={} ov={} sc={} ann={} ret={} pl={}:{} P[{}] B[{}] M[{}]",
            d.name,
            kind(d.kind),
            word(d.parent.as_ref()),
            at(&d.span),
            flag(d.exported),
            visibility(d.visibility),
            flag(d.top_level),
            flag(d.is_static),
            flag(d.is_abstract),
            flag(d.is_async),
            flag(d.decorators),
            flag(d.members_complete),
            flag(d.overload_signature),
            flag(d.signature_complete),
            word(d.annotation.as_ref()),
            word(d.returns.as_ref()),
            word(d.parent_line),
            word(d.parent_column),
            params.join(";"),
            bases.join(";"),
            members.join(";")
        ));
    }
    for b in &syntax.import_bindings {
        out.push(format!(
            "I {} {} ns={} ty={} uniq={} {}",
            b.imported,
            b.local,
            flag(b.namespace),
            flag(b.type_only),
            flag(b.source_unique),
            at(&b.span)
        ));
    }
    for (name, declaration, export) in &syntax.module_exports {
        out.push(format!("X {name} {} {}", at(declaration), at(export)));
    }
    out.push(format!("R {}", syntax.rebound_names.join(",")));
    let named = |items: &[(String, crate::syntax::Span)]| {
        items
            .iter()
            .map(|(name, span)| format!("{name}@{}", at(span)))
            .collect::<Vec<_>>()
            .join(",")
    };
    out.push(format!("G {}", named(&syntax.ambient_globals)));
    out.push(format!("T {}", named(&syntax.ambient_top_level)));
    out.push(format!(
        "F module={} declaration={} script={}",
        flag(syntax.module_file),
        flag(syntax.declaration_file),
        flag(syntax.script_mode)
    ));
    out.push(format!("B {}", syntax.script_bindings.join(",")));
    out
}

fn facts(rel: &str, text: &str) -> Vec<String> {
    let mut parsers = Parsers::new();
    summary(&parse(&mut parsers, rel, text.as_bytes()).syntax)
}

#[test]
fn class_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("class.ts", "export class A<T> extends B<T> implements C {\n  static s = 1;\n  #p = 2;\n  private q?: string;\n  constructor(public a: number, private readonly b = 2) { super(); }\n  get g() { return 1; }\n  m(x: number, ...rest: string[]): void {}\n}\n");
    let want = [
        "D A class None 1:8 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[B:inherits;<T>:inherits;C:realizes] M[s:None:None:True:1:0;#p:None:private:False:2:0;q:string:private:False:None:0;a:number:public:False:None:0;b:None:private:False:None:0]",
        "D constructor method A 5:3 ex=False vis=None top=False st=False ab=False as=False dec=False mc=False ov=False sc=False ann=None ret=None pl=1:8 P[a:number:False:False:None;b:None:False:False:2] B[] M[]",
        "D g method A 6:3 ex=False vis=None top=False st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=1:8 P[] B[] M[]",
        "D m method A 7:3 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=False ann=None ret=void pl=1:8 P[x:number:False:False:None;rest:string[]:False:True:None] B[] M[]",
        "X A 1:8 1:1",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B A",
    ];
    assert_eq!(got, want, "class.ts");
}

#[test]
fn interface_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("interface.ts", "export interface I extends J, K<string> { a: number; b?(x: T): U }\nexport enum E { A = 1, B, 'C' = 'c' }\nexport type T<U> = U extends string ? 'a' : never;\n");
    let want = [
        "D I interface None 1:8 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[J:inherits;K:inherits] M[a:number:None:False:None:0]",
        "D b method I 1:54 ex=False vis=None top=False st=False ab=False as=False dec=False mc=False ov=True sc=True ann=None ret=U pl=1:8 P[x:T:False:False:None] B[] M[]",
        "D E enum None 2:8 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[A:None:None:True:1:0;B:None:None:True:None:0;'C':None:None:True:'c':0]",
        "D T type_alias None 3:8 ex=True vis=public top=True st=False ab=False as=False dec=False mc=False ov=True sc=True ann=U extends string ? 'a' : never ret=None pl=None:None P[] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B ",
    ];
    assert_eq!(got, want, "interface.ts");
}

#[test]
fn overloads_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("overloads.ts", "function over(a: number): void;\nfunction over(a: string): void;\nfunction over(a: any) {}\nexport default function () {}\n");
    let want = [
        "D over function None 1:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=False ov=True sc=True ann=None ret=void pl=None:None P[a:number:False:False:None] B[] M[]",
        "D over function None 2:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=False ov=True sc=True ann=None ret=void pl=None:None P[a:string:False:False:None] B[] M[]",
        "D over function None 3:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[a:any:False:False:None] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B over",
    ];
    assert_eq!(got, want, "overloads.ts");
}

#[test]
fn constants_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("constants.ts", "const c1 = 1, c2 = 'x', c3 = null, c4 = id, c5 = [1, 'a', id] as const;\nexport const e1 = 2, e2 = [a, b];\nlet l1 = 1;\nclass Host { m() { const inner = 3; } }\n");
    let want = [
        "D c1 constant None 1:7 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D c2 constant None 1:15 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D c3 constant None 1:25 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D c4 constant None 1:36 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D c5 constant None 1:45 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D e1 constant None 2:14 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D e2 constant None 2:22 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D Host class None 4:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D m method Host 4:14 ex=False vis=None top=False st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=4:1 P[] B[] M[]",
        "D inner constant Host.m 4:26 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=4:14 P[] B[] M[]",
        "X e1 2:14 2:1",
        "X e2 2:22 2:1",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B Host,c1,c2,c3,c4,c5,e1,e2,l1",
    ];
    assert_eq!(got, want, "constants.ts");
}

#[test]
fn array_vs_var_ts_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "array_vs_var.ts",
        "const names = ['a', 'b'];\nif (x) { var names = 1; }\nconst other = [1];\n",
    );
    let want = [
        "D other constant None 3:7 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=False declaration=False script=False",
        "B names,other",
    ];
    assert_eq!(got, want, "array_vs_var.ts");
}

#[test]
fn imports_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("imports.ts", "import a1, { b1, type c1, d1 as e1 } from './m';\nimport * as ns1 from './n';\nimport type T1 from './t';\nimport './side';\nimport eq = require('./eq');\nfunction f() { b1 = 5; }\nns1 = 3;\nconst b1x = 1;\n");
    let want = [
        "D f function None 6:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D b1x constant None 8:7 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "I default a1 ns=False ty=False uniq=True 1:1",
        "I b1 b1 ns=False ty=False uniq=False 1:1",
        "I c1 c1 ns=False ty=True uniq=True 1:1",
        "I d1 e1 ns=False ty=False uniq=True 1:1",
        "I * ns1 ns=True ty=False uniq=False 2:1",
        "I default T1 ns=False ty=True uniq=True 3:1",
        "R ns1",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B T1,a1,b1,b1x,c1,e1,f,ns1",
    ];
    assert_eq!(got, want, "imports.ts");
}

#[test]
fn exports_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("exports.ts", "export const kept = 1;\nexport function fn() {}\nexport class Cls {}\nlet local = 2;\nexport { local };\nexport { local as renamed };\nconst twice = 1;\nexport { twice };\nexport { twice as again };\n");
    let want = [
        "D kept constant None 1:14 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D fn function None 2:8 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D Cls class None 3:8 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D twice constant None 7:7 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "X kept 1:14 1:1",
        "X fn 2:8 2:1",
        "X Cls 3:8 3:1",
        "X local 4:5 5:10",
        "X twice 7:7 8:10",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B Cls,fn,kept,local,twice",
    ];
    assert_eq!(got, want, "exports.ts");
}

#[test]
fn reexport_ts_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "reexport.ts",
        "export * from './re';\nexport const x = 1;\n",
    );
    let want = [
        "D x constant None 2:14 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B x",
    ];
    assert_eq!(got, want, "reexport.ts");
}

#[test]
fn hoisting_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("hoisting.ts", "function f(a, { b, c: [d] }, [e, ...g], h = 1, ...i) { var inner = 1; { function blk() {} } }\nvar [v2, v3] = arr;\nfor (var fv of xs) {}\nfor (let lv in ys) {}\ntry { x(); } catch ({ message }) { y = message; }\nswitch (s) { case 1: let sw = 1; }\n");
    let want = [
        "D f function None 1:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=False ov=False sc=False ann=None ret=None pl=None:None P[a:None:False:False:None;{ b, c: [d] }:None:False:False:None;[e, ...g]:None:False:False:None;h:None:False:False:1;i:None:False:True:None] B[] M[]",
        "R y",
        "G ",
        "T ",
        "F module=False declaration=False script=False",
        "B f,fv,v2,v3",
    ];
    assert_eq!(got, want, "hoisting.ts");
}

#[test]
fn rebound_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("rebound.ts", "reassigned = 1;\nreassigned += 2;\nfunction f() { inside = 1; }\nconst arrow = () => { inner2 = 2; };\n[pa, pb] = [1, 2];\nclass K { m() { viaMethod = 1; } }\nlet last: number; last = 9;\n");
    let want = [
        "D f function None 3:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D K class None 6:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D m method K 6:11 ex=False vis=None top=False st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=6:1 P[] B[] M[]",
        "R last,reassigned",
        "G ",
        "T ",
        "F module=False declaration=False script=False",
        "B K,arrow,f,last",
    ];
    assert_eq!(got, want, "rebound.ts");
}

#[test]
fn ambient_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("ambient.ts", "declare global { const gv: number; var gw: string; function gf(): void; namespace GN {} }\ndeclare const dc: number;\ndeclare function df(): void;\ndeclare class DC {}\ndeclare module 'm';\ndeclare namespace NS.Inner { const x: number; }\n");
    let want = [
        "D df function None 3:9 ex=False vis=None top=False st=False ab=False as=False dec=False mc=False ov=True sc=True ann=None ret=void pl=None:None P[] B[] M[]",
        "D DC class None 4:9 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "R ",
        "G gv@1:24,gw@1:40,gf@1:61,GN@1:83",
        "T dc@2:15,df@3:18,DC@4:15,NS@6:19",
        "F module=False declaration=False script=False",
        "B DC,dc,gw",
    ];
    assert_eq!(got, want, "ambient.ts");
}

#[path = "walk_cases_tests.rs"]
mod cases;

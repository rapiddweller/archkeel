// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the syntax walk. More sources with the lines that `parse.parse()` prints for them.

use super::facts;

#[test]
fn ambient_module_ts_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "ambient_module.ts",
        "import x from './x';\ndeclare const dc: number;\ndeclare global { const gv: number }\n",
    );
    let want = [
        "I default x ns=False ty=False uniq=True 1:1",
        "R ",
        "G gv@3:24",
        "T ",
        "F module=True declaration=False script=False",
        "B dc,x",
    ];
    assert_eq!(got, want, "ambient_module.ts");
}

#[test]
fn namespace_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("namespace.ts", "namespace Outer { export class InNs {} const k = 1; }\nmodule Legacy { function innerFn() {} }\nclass After {}\n");
    let want = [
        "D k constant None 1:46 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D innerFn function None 2:17 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D After class None 3:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=False declaration=False script=False",
        "B After,innerFn",
    ];
    assert_eq!(got, want, "namespace.ts");
}

#[test]
fn script_js_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "script.js",
        "var top = 1;\nfunction helper() { return top; }\ntop = 2;\n",
    );
    let want = [
        "D helper function None 2:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "R top",
        "G ",
        "T ",
        "F module=False declaration=False script=True",
        "B helper,top",
    ];
    assert_eq!(got, want, "script.js");
}

#[test]
fn module_mjs_has_the_syntax_of_the_python_parser() {
    let got = facts("module.mjs", "var top = 1;\n");
    let want = [
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B top",
    ];
    assert_eq!(got, want, "module.mjs");
}

#[test]
fn decl_d_ts_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "decl.d.ts",
        "declare const D: number;\ninterface Win { a: number }\n",
    );
    let want = [
        "D Win interface None 2:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[a:number:None:False:None:0]",
        "R ",
        "G ",
        "T D@1:15",
        "F module=False declaration=True script=False",
        "B D",
    ];
    assert_eq!(got, want, "decl.d.ts");
}

#[test]
fn decorators_ts_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "decorators.ts",
        "@Component({}) export class Decorated {}\nclass W { @a @b() prop = 1; @c method() {} }\n",
    );
    let want = [
        "D Decorated class None 1:23 ex=True vis=public top=True st=False ab=False as=False dec=True mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D W class None 2:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[prop:None:None:False:1:2]",
        "D method method W 2:32 ex=False vis=None top=False st=False ab=False as=False dec=True mc=True ov=False sc=True ann=None ret=None pl=2:1 P[] B[] M[]",
        "X Decorated 1:23 1:1",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B Decorated,W",
    ];
    assert_eq!(got, want, "decorators.ts");
}

#[test]
fn gen_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("gen.ts", "class Gen { *g() {} async am() {} static async *sg() {} 'constructor'() {} }\nfunction* gf() {}\nasync function af() {}\n");
    let want = [
        "D Gen class None 1:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D g method Gen 1:13 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=1:1 P[] B[] M[]",
        "D am method Gen 1:21 ex=False vis=None top=False st=False ab=False as=True dec=False mc=True ov=False sc=True ann=None ret=None pl=1:1 P[] B[] M[]",
        "D sg method Gen 1:35 ex=False vis=None top=False st=True ab=False as=True dec=False mc=True ov=False sc=True ann=None ret=None pl=1:1 P[] B[] M[]",
        "D constructor method Gen 1:57 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=1:1 P[] B[] M[]",
        "D af function None 3:1 ex=False vis=None top=True st=False ab=False as=True dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=False declaration=False script=False",
        "B Gen,af,gf",
    ];
    assert_eq!(got, want, "gen.ts");
}

#[test]
fn escapes_ts_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "escapes.ts",
        "class Esc { 'cons\\x74ructor'() {} \\u0061() {} }\nconst \\u0062c = 1;\n",
    );
    let want = [
        "D Esc class None 1:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D 'cons\\x74ructor' method Esc 1:13 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=1:1 P[] B[] M[]",
        "D \\u0061 method Esc 1:35 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=1:1 P[] B[] M[]",
        "D \\u0062c constant None 2:7 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=False declaration=False script=False",
        "B Esc",
    ];
    assert_eq!(got, want, "escapes.ts");
}

#[test]
fn members_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("members.ts", "enum Plain { A, B }\nclass Props { x: number = 1; y = 'two'; static z = true; readonly w; }\ninterface Sig { a: number; b(): void; [k: string]: any }\n");
    let want = [
        "D Plain enum None 1:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[A:None:None:True:None:0;B:None:None:True:None:0]",
        "D Props class None 2:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[x:number:None:False:1:0;y:None:None:False:'two':0;z:None:None:True:true:0;w:None:None:False:None:0]",
        "D Sig interface None 3:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[a:number:None:False:None:0]",
        "D b method Sig 3:28 ex=False vis=None top=False st=False ab=False as=False dec=False mc=False ov=True sc=True ann=None ret=void pl=3:1 P[] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=False declaration=False script=False",
        "B Props",
    ];
    assert_eq!(got, want, "members.ts");
}

#[test]
fn broken_ts_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "broken.ts",
        "export class Ok { m() {} }\nconst ( = ;\nfunction after() {}\n",
    );
    let want = [
        "D Ok class None 1:8 ex=True vis=public top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D m method Ok 1:19 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=1:8 P[] B[] M[]",
        "D after function None 3:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B Ok,after",
    ];
    assert_eq!(got, want, "broken.ts");
}

#[test]
fn tsx_tsx_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "tsx.tsx",
        "export const View = (p: P) => <div>{p.x}</div>;\nfunction Comp() { return <A />; }\n",
    );
    let want = [
        "D Comp function None 2:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "X View 1:14 1:1",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B Comp,View",
    ];
    assert_eq!(got, want, "tsx.tsx");
}

#[test]
fn reexport_local_ts_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "reexport_local.ts",
        "function x() {}\nclass K {}\nexport { x } from './m';\nexport { K as KK } from './n';\n",
    );
    let want = [
        "D x function None 1:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D K class None 2:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B K,x",
    ];
    assert_eq!(got, want, "reexport_local.ts");
}

#[test]
fn decorated_ctor_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("decorated_ctor.ts", "class D1 { @d constructor(public a: number) {} }\nclass D2 { @d\n// c\n@e() /* b */ constructor(private readonly b = 1) {} m() {} }\nclass D3 { // c\nconstructor(public a: number) {} @d m(x: number) {} }\n");
    let want = [
        "D D1 class None 1:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D constructor method D1 1:15 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=1:1 P[a:number:False:False:None] B[] M[]",
        "D D2 class None 2:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D constructor method D2 4:14 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=False ann=None ret=None pl=2:1 P[b:None:False:False:1] B[] M[]",
        "D m method D2 4:53 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=2:1 P[] B[] M[]",
        "D D3 class None 5:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[a:number:public:False:None:0]",
        "D constructor method D3 6:1 ex=False vis=None top=False st=False ab=False as=False dec=False mc=True ov=False sc=True ann=None ret=None pl=5:1 P[a:number:False:False:None] B[] M[]",
        "D m method D3 6:37 ex=False vis=None top=False st=False ab=False as=False dec=True mc=True ov=False sc=True ann=None ret=None pl=5:1 P[x:number:False:False:None] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=False declaration=False script=False",
        "B D1,D2,D3",
    ];
    assert_eq!(got, want, "decorated_ctor.ts");
}

#[test]
fn sibling_writes_ts_has_the_syntax_of_the_python_parser() {
    let got = facts("sibling_writes.ts", "import a from './a';\nfunction f() { var a; a = 1; }\nfunction g() { a = 2; }\nimport b from './b';\nfunction h() { b = 2; }\nfunction k() { var b; b = 1; }\n");
    let want = [
        "D f function None 2:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D g function None 3:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D h function None 5:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "D k function None 6:1 ex=False vis=private top=True st=False ab=False as=False dec=False mc=False ov=False sc=True ann=None ret=None pl=None:None P[] B[] M[]",
        "I default a ns=False ty=False uniq=False 1:1",
        "I default b ns=False ty=False uniq=False 4:1",
        "R ",
        "G ",
        "T ",
        "F module=True declaration=False script=False",
        "B a,b,f,g,h,k",
    ];
    assert_eq!(got, want, "sibling_writes.ts");
}

#[test]
fn pattern_bound_ts_has_the_syntax_of_the_python_parser() {
    let got = facts(
        "pattern_bound.ts",
        "const { d1, d2: [d3] } = o, [d4, ...d5] = arr;\nfunction g({ a = 1 }, [b], c = 2) {}\n",
    );
    let want = [
        "D g function None 2:1 ex=False vis=None top=True st=False ab=False as=False dec=False mc=True ov=False sc=False ann=None ret=None pl=None:None P[{ a = 1 }:None:False:False:None;[b]:None:False:False:None;c:None:False:False:2] B[] M[]",
        "R ",
        "G ",
        "T ",
        "F module=False declaration=False script=False",
        "B d1,d3,d4,d5,g",
    ];
    assert_eq!(got, want, "pattern_bound.ts");
}

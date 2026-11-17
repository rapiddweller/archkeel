// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: AD-550. The model decides `boundary_types` from these shapes, so each written form
// has a row: accepted, refused or named. A name is proven by the binding in scope, never by its
// spelling.

use archkeel_facts::type_shape::{Binding, TypeShape};
use archkeel_facts::{FactData, SymbolFact};

use crate::survey::targets::tests::surveyed;

/// One line for a shape: the form, the binding of a name, the arms and the arguments.
fn brief(shape: &TypeShape) -> String {
    let list = |items: &[TypeShape]| items.iter().map(brief).collect::<Vec<_>>().join(", ");
    match shape {
        TypeShape::Unannotated {} => "missing".to_owned(),
        TypeShape::Nothing {} => "none".to_owned(),
        TypeShape::Primitive { name, .. } => format!("prim:{name}"),
        TypeShape::Dynamic { name, .. } => format!("dyn:{name}"),
        TypeShape::Collection {
            name,
            args,
            open_end,
            ..
        } => format!(
            "{name}[{}{}]",
            list(args),
            if *open_end { ", ..." } else { "" }
        ),
        TypeShape::Union { arms, .. } => format!("union({})", list(arms)),
        TypeShape::Literal { plain, .. } => format!("literal:{plain}"),
        TypeShape::Annotated { inner, .. } => format!("annotated({})", brief(inner)),
        TypeShape::Named { binding, .. } => match binding {
            Binding::Builtin { target } => format!("builtin:{target}"),
            Binding::Defined { target } => format!("defined:{target}"),
            Binding::Imported { target } => format!("imported:{target}"),
            Binding::Unproven { cause } => format!("unproven:{}", cause.as_str()),
        },
        TypeShape::Applied { head, args, .. } => format!("apply({})[{}]", brief(head), list(args)),
        TypeShape::Forward { text } => format!("forward:{text}"),
        TypeShape::Unreadable { cause, .. } => format!("unreadable:{}", cause.as_str()),
    }
}

/// The shapes of the positions of `app.m.<name>`: the parameters in order, then the return.
fn positions(source: &str, name: &str) -> Vec<String> {
    positions_with(source, name, &[])
}

fn positions_with(source: &str, name: &str, more: &[(&str, &str)]) -> Vec<String> {
    let mut files = vec![("src/app/__init__.py", ""), ("src/app/m.py", source)];
    files.extend_from_slice(more);
    let found = surveyed(&files);
    let want = format!("app.m.{name}");
    for record in &found.symbols {
        let (SymbolFact::Function(data) | SymbolFact::Method(data)) = &record.data else {
            continue;
        };
        if data.qualified_name != want {
            continue;
        }
        let mut shown: Vec<String> = data
            .parameters
            .iter()
            .map(|item| item.shape.as_ref().map_or("none-written".to_owned(), brief))
            .collect();
        shown.push(
            data.returns_shape
                .as_ref()
                .map_or("none-written".to_owned(), brief),
        );
        return shown;
    }
    vec!["no record".to_owned()]
}

#[test]
fn a_builtin_that_no_statement_hides_is_a_primitive() {
    let found = positions(
        "def f(a: int, b: str, c: bytes, d: bool, e: float) -> None: ...\n",
        "f",
    );
    assert_eq!(
        found,
        [
            "prim:int",
            "prim:str",
            "prim:bytes",
            "prim:bool",
            "prim:float",
            "none"
        ]
    );
}

#[test]
fn a_builtin_that_the_module_rebinds_is_not_a_builtin() {
    let rebound = positions("int = str\n\n\ndef f(a: int): ...\n", "f");
    assert_eq!(rebound[0], "defined:app.m.int");
    let twice = positions("int = str\nint = bytes\n\n\ndef f(a: int): ...\n", "f");
    assert_eq!(twice[0], "unproven:not_sole");
    let hidden = positions(
        "class C:\n    int = 1\n\n    def f(self, a: int): ...\n",
        "C.f",
    );
    assert_eq!(hidden[1], "unproven:hidden");
}

#[test]
fn an_unannotated_position_is_written_as_missing_and_the_variadics_are_positions() {
    let found = positions("def f(a, *args, k=1, **kwargs): ...\n", "f");
    assert_eq!(
        found,
        ["missing", "missing", "missing", "missing", "missing"]
    );
    let typed = positions("def g(*args: int, **kwargs: str) -> int: ...\n", "g");
    assert_eq!(typed, ["prim:int", "prim:str", "prim:int"]);
}

#[test]
fn object_and_any_are_dynamic_and_only_by_binding() {
    let source =
        "from typing import Any\nimport typing\n\n\ndef f(a: object, b: Any, c: typing.Any): ...\n";
    assert_eq!(
        positions(source, "f"),
        ["dyn:object", "dyn:Any", "dyn:Any", "missing"]
    );
    let fake = "from app.other import Any\n\n\ndef f(a: Any): ...\n";
    let found = positions_with(fake, "f", &[("src/app/other.py", "Any = int\n")]);
    assert_eq!(found[0], "imported:app.other.Any");
}

#[test]
fn collections_carry_their_arguments_and_a_bare_name_has_none() {
    let source = "from typing import Sequence, Mapping, List\n\n\ndef f(a: list[int], b: dict[str, int], c: tuple[int, ...], d: tuple[int, str], e: dict, g: Sequence[str], h: Mapping[str, int], i: List[int]): ...\n";
    assert_eq!(
        positions(source, "f"),
        [
            "list[prim:int]",
            "dict[prim:str, prim:int]",
            "tuple[prim:int, ...]",
            "tuple[prim:int, prim:str]",
            "dict[]",
            "Sequence[prim:str]",
            "Mapping[prim:str, prim:int]",
            "List[prim:int]",
            "missing"
        ]
    );
}

#[test]
fn a_union_is_flat_and_optional_adds_nothing() {
    let source = "from typing import Optional, Union\n\n\ndef f(a: int | str | None, b: Optional[int], c: Union[int, str], d: Union[int, None]): ...\n";
    assert_eq!(
        positions(source, "f"),
        [
            "union(prim:int, prim:str, none)",
            "union(prim:int, none)",
            "union(prim:int, prim:str)",
            "union(prim:int, none)",
            "missing"
        ]
    );
}

#[test]
fn a_special_form_is_read_by_its_binding_not_its_spelling() {
    let source = "from app.other import Optional\n\n\ndef f(a: Optional[int]): ...\n";
    let found = positions_with(source, "f", &[("src/app/other.py", "Optional = list\n")]);
    assert_eq!(found[0], "apply(imported:app.other.Optional)[prim:int]");
}

#[test]
fn annotated_keeps_the_inner_type_and_literal_says_whether_it_is_plain() {
    let source = "from typing import Annotated, Literal\n\n\ndef f(a: Annotated[int, 'm'], b: Literal['x', 1, None], c: Literal[Color.RED]): ...\n";
    let found = positions(source, "f");
    assert_eq!(found[0], "annotated(prim:int)");
    assert_eq!(found[1], "literal:true");
    assert_eq!(found[2], "literal:false");
}

#[test]
fn a_string_annotation_is_forward_unless_it_is_a_builtin_that_nothing_hides() {
    let found = positions("def f(a: 'str', b: 'Later', c: 'object'): ...\n", "f");
    assert_eq!(
        found,
        ["prim:str", "forward:'Later'", "dyn:object", "missing"]
    );
    let rebound = positions("str = int\n\n\ndef f(a: 'str'): ...\n", "f");
    assert_eq!(rebound[0], "forward:'str'");
}

#[test]
fn a_name_is_proven_by_one_plain_binder_and_the_cause_names_the_rest() {
    let source = "from app.other import Thing\nfrom app.third import *\n\n\ndef f(a: Thing): ...\n";
    let star = positions_with(
        source,
        "f",
        &[
            ("src/app/other.py", "class Thing: ...\n"),
            ("src/app/third.py", "X = 1\n"),
        ],
    );
    // The module gate of AD-518 withholds each record of a module with a star import.
    assert_eq!(star, ["no record"]);
    let plain = "from app.other import Thing\n\n\nclass Local: ...\n\n\ndef f(a: Thing, b: Local, c: Missing): ...\n";
    let found = positions_with(plain, "f", &[("src/app/other.py", "class Thing: ...\n")]);
    assert_eq!(
        found,
        [
            "imported:app.other.Thing",
            "defined:app.m.Local",
            "unproven:unbound",
            "missing"
        ]
    );
}

#[test]
fn a_name_bound_twice_or_under_a_condition_is_not_proven() {
    let twice = positions(
        "class A: ...\n\n\nclass A: ...\n\n\ndef f(a: A): ...\n",
        "f",
    );
    assert_eq!(twice[0], "unproven:not_sole");
    let guarded = "try:\n    from app.other import A\nexcept ImportError:\n    A = int\n\n\ndef f(a: A): ...\n";
    let found = positions_with(guarded, "f", &[("src/app/other.py", "class A: ...\n")]);
    assert_eq!(found[0], "unproven:not_sole");
}

#[test]
fn a_dotted_name_is_proven_only_through_one_plain_module_import() {
    let source = "import app.other as other\nimport app.third\n\n\ndef f(a: other.Thing, b: app.third.Thing, c: other.sub.Thing): ...\n";
    let more = [
        ("src/app/other.py", "class Thing: ...\n"),
        ("src/app/third.py", "class Thing: ...\n"),
    ];
    let found = positions_with(source, "f", &more);
    assert_eq!(found[0], "imported:app.other.Thing");
    assert_eq!(found[1], "unproven:dotted");
    assert_eq!(found[2], "unproven:dotted");
}

#[test]
fn a_user_generic_and_a_callable_type_are_not_modeled() {
    let source = "from typing import Callable\n\n\nclass Box: ...\n\n\ndef f(a: Box[int], b: Callable[[int], str]): ...\n";
    let found = positions(source, "f");
    assert_eq!(found[0], "apply(defined:app.m.Box)[prim:int]");
    assert_eq!(
        found[1],
        "apply(imported:typing.Callable)[unreadable:not_a_type_form, prim:str]"
    );
}

#[test]
fn a_type_parameter_hides_a_module_name_in_the_annotation() {
    let found = positions("class T: ...\n\n\ndef f[T](a: T) -> T: ...\n", "f");
    assert_eq!(found, ["unproven:hidden", "unproven:hidden"]);
}

#[test]
fn a_class_attribute_with_a_subscript_does_not_withhold_the_module() {
    let source = "class C:\n    items: list[int] = []\n\n    def m(self, a: list[int]) -> int: ...\n\n\ndef f(a: dict[str, int]): ...\n";
    assert_eq!(positions(source, "f")[0], "dict[prim:str, prim:int]");
}

#[test]
fn a_function_with_an_unwritable_text_still_has_shapes_and_an_incomplete_signature() {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        (
            "src/app/m.py",
            "def f(a: list[int], b=lambda: 1) -> int: ...\n",
        ),
    ]);
    let record = found
        .symbols
        .iter()
        .find_map(|record| match &record.data {
            SymbolFact::Function(data) if data.name == "f" => Some(data),
            _ => None,
        })
        .expect("the function has a record");
    assert_eq!(record.signature_complete, Some(false));
    assert!(record.parameters.iter().all(|item| item.shape.is_some()));
}

#[test]
fn a_decorated_function_has_no_record_and_so_no_shape() {
    let source = "import functools\n\n\n@functools.cache\ndef f(a: int): ...\n";
    assert_eq!(positions(source, "f"), ["no record"]);
}

#[test]
fn a_dataclass_has_no_record_and_so_no_shape_for_its_fields() {
    let source = "from dataclasses import dataclass\n\n\n@dataclass\nclass D:\n    x: int\n\n\ndef f(a: D) -> D: ...\n";
    let found = positions(source, "f");
    assert_eq!(found, ["defined:app.m.D", "defined:app.m.D"]);
    let symbols = surveyed(&[("src/app/__init__.py", ""), ("src/app/m.py", source)]).symbols;
    assert!(symbols
        .iter()
        .all(|record| record.data.fields().qualified_name != Some("app.m.D")));
}

#[test]
fn an_import_of_a_module_that_another_module_writes_is_not_the_one_binder() {
    let found = surveyed(&[
        ("src/app/__init__.py", ""),
        ("src/app/api.py", "from app.inner import f\n"),
        ("src/app/inner.py", "def f(a: dict) -> int:\n    return 1\n"),
        (
            "src/app/other.py",
            "import app.api as api\n\napi.f = lambda a: a\n",
        ),
    ]);
    let unique = |module: &str| {
        found
            .imports
            .iter()
            .filter(|record| record.data.data().source_module.as_str() == module)
            .map(|record| record.data.data().source_binding_unique)
            .collect::<Vec<_>>()
    };
    assert_eq!(unique("app.api"), [Some(false)]);
    assert_eq!(unique("app.other"), [Some(true)]);
}

/// #1523: on Python 3.14 (the target of these trees) a method annotation reads the namespace of its
/// class when it is evaluated. A slot or an attribute store can put the name there.
#[test]
fn a_lazy_method_annotation_is_unproven_when_the_class_namespace_can_hold_the_name() {
    let method = |head: &str, more: &[(&str, &str)]| {
        let source = format!("class Box:\n{head}    def f(self, x: object) -> int: return 1\n");
        positions_with(&source, "Box.f", more)
    };
    let lazy = "unproven:lazy_class_namespace";
    assert_eq!(method("    __slots__ = ('object',)\n", &[])[1], lazy);
    assert_eq!(method("    __slots__ = names()\n", &[])[1], lazy);
    // A store in a file outside the scan roots, and a store with a computed name.
    let outside = ("tools/patch.py", "import app.m\napp.m.Box.object = int\n");
    assert_eq!(method("", &[outside])[1], lazy);
    let computed = ("src/app/w.py", "def put(o, n, v):\n    setattr(o, n, v)\n");
    assert_eq!(method("", &[computed])[1], lazy);
    // `int` is no stored name and no slot: still proven.
    assert_eq!(method("    __slots__ = ('object',)\n", &[])[2], "prim:int");
}

#[test]
fn a_method_annotation_without_a_namespace_write_or_with_future_annotations_is_proven() {
    let source = "class Box:\n    def f(self, x: object) -> int: return 1\n";
    assert_eq!(positions(source, "Box.f")[1], "dyn:object");
    // A store from a test file is under the stated premise (AD-770).
    let test = (
        "tests/test_patch.py",
        "import app.m\napp.m.Box.object = int\n",
    );
    assert_eq!(positions_with(source, "Box.f", &[test])[1], "dyn:object");
    // A store of another name.
    let other = ("tools/p.py", "import app.m\napp.m.Box.other = 1\n");
    assert_eq!(positions_with(source, "Box.f", &[other])[1], "dyn:object");
    // A module function reads no class namespace.
    let write = ("src/app/w.py", "import app.m\napp.m.Box.object = int\n");
    let function = "class Box: ...\ndef g(x: object) -> int: return 1\n";
    assert_eq!(positions_with(function, "g", &[write])[0], "dyn:object");
    let future =
        format!("from __future__ import annotations\n{source}    __slots__ = ('object',)\n");
    assert_ne!(
        positions(&future, "Box.f")[1],
        "unproven:lazy_class_namespace"
    );
}

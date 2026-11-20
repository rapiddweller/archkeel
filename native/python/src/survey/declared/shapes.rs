// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shape of each written type of a signature (AD-550): the annotation of a parameter and the
//! return annotation of each function and method that has a record.
//!
//! The shape is read from the syntax. It keeps no text that the model must parse, and it states a
//! binding only when `shape_names` proves it. A form that the collector does not model (a call, a
//! callable type, a list of types) is `Unreadable` and a user generic is `Applied`: the model reads
//! both as a named gap and never as a plain type.

use crate::module::builtin_roles::{self, Role};
use std::collections::{HashMap, HashSet};

use archkeel_facts::ids::ModuleName;
use archkeel_facts::type_shape::{Binding, Family, TypeShape, Unreadable};
use archkeel_facts::{ImportFact, Record, SymbolFact};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, Number, Operator, Stmt, UnaryOp};

use super::found::{Found, Source};
use super::scope::type_names;
use super::shape_names::{Hidden, Lazy, Names};
use super::shape_text::render;
use crate::module::Module;
use crate::survey::binders::Binders;
use crate::survey::class_writes::{future_annotations, ClassWrites};

/// The deepest type expression that the reader follows.
const MAX_DEPTH: u32 = 24;

/// The collections of the language and of its standard library, by qualified name.
const COLLECTIONS: &[(&str, Family)] = &[
    ("list", Family::Sequence),
    ("set", Family::Sequence),
    ("frozenset", Family::Sequence),
    ("tuple", Family::Sequence),
    ("dict", Family::Mapping),
    ("typing.List", Family::Sequence),
    ("typing.Set", Family::Sequence),
    ("typing.FrozenSet", Family::Sequence),
    ("typing.Tuple", Family::Sequence),
    ("typing.Sequence", Family::Sequence),
    ("typing.MutableSequence", Family::Sequence),
    ("typing.Iterable", Family::Sequence),
    ("typing.Iterator", Family::Sequence),
    ("typing.Collection", Family::Sequence),
    ("typing.AbstractSet", Family::Sequence),
    ("typing.MutableSet", Family::Sequence),
    ("typing.Deque", Family::Sequence),
    ("typing.Dict", Family::Mapping),
    ("typing.Mapping", Family::Mapping),
    ("typing.MutableMapping", Family::Mapping),
    ("typing.DefaultDict", Family::Mapping),
    ("typing.OrderedDict", Family::Mapping),
    ("typing_extensions.OrderedDict", Family::Mapping),
    ("collections.abc.Sequence", Family::Sequence),
    ("collections.abc.MutableSequence", Family::Sequence),
    ("collections.abc.Iterable", Family::Sequence),
    ("collections.abc.Iterator", Family::Sequence),
    ("collections.abc.Collection", Family::Sequence),
    ("collections.abc.Set", Family::Sequence),
    ("collections.abc.MutableSet", Family::Sequence),
    ("collections.abc.Mapping", Family::Mapping),
    ("collections.abc.MutableMapping", Family::Mapping),
    ("collections.deque", Family::Sequence),
    ("collections.defaultdict", Family::Mapping),
    ("collections.OrderedDict", Family::Mapping),
    ("typing_extensions.List", Family::Sequence),
    ("typing_extensions.Dict", Family::Mapping),
    ("typing_extensions.Sequence", Family::Sequence),
    ("typing_extensions.Mapping", Family::Mapping),
    ("typing_extensions.Iterable", Family::Sequence),
];

/// The qualified names of the collections, for the names of the standard library (AD-782).
pub(crate) fn collection_names() -> Vec<&'static str> {
    COLLECTIONS.iter().map(|(name, _)| *name).collect()
}

/// The special forms of `typing` that the shape reader normalizes (#1718): a union, an optional,
/// a literal and an annotation. They hold no data of their own; their arguments decide.
pub(crate) const FORMS: [&str; 8] = [
    "typing.Optional",
    "typing.Union",
    "typing.Literal",
    "typing.Annotated",
    "typing_extensions.Optional",
    "typing_extensions.Union",
    "typing_extensions.Literal",
    "typing_extensions.Annotated",
];

/// True for a collection or a special form that the shape reader reads by its qualified name: the
/// premise must hold for it (#1718). A builtin of the language has no module and is not one.
pub(super) fn read_by_name(target: &str) -> bool {
    FORMS.contains(&target)
        || (target.contains('.') && COLLECTIONS.iter().any(|(name, _)| *name == target))
}

/// The special forms of `typing` that the shape normalizes.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Form {
    Optional,
    Union,
    Annotated,
    Literal,
    Any,
}

fn form(target: &str) -> Option<Form> {
    let (module, name) = target.rsplit_once('.')?;
    if module != "typing" && module != "typing_extensions" {
        return None;
    }
    Some(match name {
        "Optional" => Form::Optional,
        "Union" => Form::Union,
        "Annotated" => Form::Annotated,
        "Literal" => Form::Literal,
        "Any" => Form::Any,
        _ => return None,
    })
}

/// The reader of the written types of one module.
pub(super) struct Shaper<'a> {
    pub(super) names: &'a Names<'a>,
    /// On Python 3.14 without `from __future__ import annotations`: the stores that can give a
    /// class namespace a name after its statement (#1523).
    pub(super) lazy: Option<&'a ClassWrites>,
}

impl Shaper<'_> {
    /// The shapes of the positions of `source`: one for each parameter in the order of the
    /// signature, and the return.
    pub(super) fn signature(&self, source: &Source<'_>) -> (Vec<TypeShape>, TypeShape) {
        let mut names: HashSet<String> = source.class_names.clone().unwrap_or_default();
        names.extend(type_names(source.node));
        // A method annotation reads the namespace of its class when it is evaluated (PEP 649).
        let lazy = (self.lazy)
            .filter(|_| source.class_names.is_some())
            .map(|writes| Lazy {
                slots: source.slots.as_ref(),
                writes,
            });
        let hidden = Hidden { names, lazy };
        let params = &source.node.parameters;
        let positional = params.posonlyargs.iter().chain(&params.args);
        let mut found: Vec<TypeShape> = positional
            .map(|item| self.position(item.parameter.annotation.as_deref(), &hidden))
            .collect();
        found.extend(
            params
                .vararg
                .iter()
                .map(|item| self.position(item.annotation.as_deref(), &hidden)),
        );
        found.extend(
            params
                .kwonlyargs
                .iter()
                .map(|item| self.position(item.parameter.annotation.as_deref(), &hidden)),
        );
        found.extend(
            params
                .kwarg
                .iter()
                .map(|item| self.position(item.annotation.as_deref(), &hidden)),
        );
        let returns = self.position(source.node.returns.as_deref(), &hidden);
        (found, returns)
    }

    pub(super) fn position(&self, annotation: Option<&Expr>, hidden: &Hidden<'_>) -> TypeShape {
        annotation.map_or(TypeShape::Unannotated {}, |expr| {
            self.shape(expr, hidden, 0)
        })
    }

    fn shape(&self, expr: &Expr, hidden: &Hidden<'_>, depth: u32) -> TypeShape {
        if depth > MAX_DEPTH {
            return unreadable(String::new(), Unreadable::TooDeep);
        }
        let Some(text) = render(expr) else {
            return unreadable(String::new(), Unreadable::TextUnwritable);
        };
        match expr {
            Expr::NoneLiteral(_) => TypeShape::Nothing {},
            Expr::StringLiteral(node) => self.quoted(node.value.to_str(), text, hidden),
            Expr::Name(_) | Expr::Attribute(_) => self.named(expr, text, hidden),
            Expr::Subscript(node) => self.applied(&node.value, &node.slice, text, hidden, depth),
            Expr::BinOp(node) if node.op == Operator::BitOr => {
                let mut arms = Vec::new();
                self.arms(expr, hidden, depth, &mut arms);
                TypeShape::Union { text, arms }
            }
            _ => unreadable(text, Unreadable::NotATypeForm),
        }
    }

    /// The arms of a chain `A | B | C`, flattened.
    fn arms(&self, expr: &Expr, hidden: &Hidden<'_>, depth: u32, out: &mut Vec<TypeShape>) {
        match expr {
            Expr::BinOp(node) if node.op == Operator::BitOr => {
                self.arms(&node.left, hidden, depth + 1, out);
                self.arms(&node.right, hidden, depth + 1, out);
            }
            other => out.push(self.shape(other, hidden, depth + 1)),
        }
    }

    /// A string annotation. Only a builtin that no statement hides reads as itself, as in
    /// release 4.0.1; any other string is a forward reference that nothing here resolves.
    fn quoted(&self, value: &str, text: String, hidden: &Hidden<'_>) -> TypeShape {
        let word = value.trim();
        if (word == "str" || word == "object")
            && matches!(self.names.name(word, hidden), Binding::Builtin { .. })
        {
            return builtin(word, word.to_owned());
        }
        TypeShape::Forward { text }
    }

    fn named(&self, expr: &Expr, text: String, hidden: &Hidden<'_>) -> TypeShape {
        let binding = self.names.binding(expr, hidden);
        match &binding {
            Binding::Builtin { target } if builtin_roles::has(target.as_str(), Role::PRIMITIVE) => {
                TypeShape::Primitive {
                    name: target.clone(),
                    text,
                }
            }
            Binding::Builtin { target } if target == "object" => TypeShape::Dynamic {
                name: target.clone(),
                text,
            },
            Binding::Builtin { target } | Binding::Imported { target } => {
                if form(target) == Some(Form::Any) {
                    return TypeShape::Dynamic {
                        name: "Any".to_owned(),
                        text,
                    };
                }
                match collection(target) {
                    Some((family, name)) => TypeShape::Collection {
                        text,
                        family,
                        name,
                        args: Vec::new(),
                        open_end: false,
                    },
                    None => TypeShape::Named { text, binding },
                }
            }
            _ => TypeShape::Named { text, binding },
        }
    }

    fn applied(
        &self,
        head: &Expr,
        slice: &Expr,
        text: String,
        hidden: &Hidden<'_>,
        depth: u32,
    ) -> TypeShape {
        let args: Vec<&Expr> = match slice {
            Expr::Tuple(node) => node.elts.iter().collect(),
            other => vec![other],
        };
        let binding = match head {
            Expr::Name(_) | Expr::Attribute(_) => Some(self.names.binding(head, hidden)),
            _ => None,
        };
        let target = match &binding {
            Some(Binding::Builtin { target } | Binding::Imported { target }) => Some(target),
            _ => None,
        };
        let shapes = |items: &[&Expr]| -> Vec<TypeShape> {
            items
                .iter()
                .map(|item| self.shape(item, hidden, depth + 1))
                .collect()
        };
        if let Some(found) = target.and_then(|target| form(target)) {
            match (found, args.as_slice()) {
                (Form::Optional, [one]) => {
                    let arms = vec![self.shape(one, hidden, depth + 1), TypeShape::Nothing {}];
                    return TypeShape::Union { text, arms };
                }
                (Form::Union, items) if !items.is_empty() => {
                    return TypeShape::Union {
                        text,
                        arms: shapes(items),
                    };
                }
                (Form::Annotated, [first, _, ..]) => {
                    return TypeShape::Annotated {
                        text,
                        inner: Box::new(self.shape(first, hidden, depth + 1)),
                    };
                }
                (Form::Literal, items) if !items.is_empty() => {
                    let plain = items.iter().all(|item| plain_constant(item));
                    return TypeShape::Literal { text, plain };
                }
                _ => {}
            }
        }
        if let Some((family, name)) = target.and_then(|target| collection(target)) {
            return collection_shape(text, (family, name), &args, &shapes);
        }
        let head_shape = self.shape(head, hidden, depth + 1);
        TypeShape::Applied {
            text,
            head: Box::new(head_shape),
            args: shapes(&args),
        }
    }
}

fn collection_shape(
    text: String,
    (family, name): (Family, String),
    args: &[&Expr],
    shapes: &dyn Fn(&[&Expr]) -> Vec<TypeShape>,
) -> TypeShape {
    let open_end = family == Family::Sequence
        && name.eq_ignore_ascii_case("tuple")
        && matches!(args, [_, Expr::EllipsisLiteral(_)]);
    let counted = if open_end { &args[..1] } else { args };
    let empty = args.is_empty();
    if empty
        || args
            .iter()
            .any(|item| matches!(item, Expr::EllipsisLiteral(_)))
            && !open_end
    {
        return unreadable(text, Unreadable::NotATypeForm);
    }
    TypeShape::Collection {
        text,
        family,
        name,
        args: shapes(counted),
        open_end,
    }
}

fn collection(target: &str) -> Option<(Family, String)> {
    let (_, family) = COLLECTIONS.iter().find(|(name, _)| *name == target)?;
    let name = target.rsplit('.').next().unwrap_or(target);
    Some((*family, name.to_owned()))
}

fn plain_constant(expr: &Expr) -> bool {
    match expr {
        Expr::StringLiteral(_)
        | Expr::BytesLiteral(_)
        | Expr::BooleanLiteral(_)
        | Expr::NoneLiteral(_) => true,
        Expr::NumberLiteral(node) => matches!(node.value, Number::Int(_)),
        Expr::UnaryOp(node) => {
            node.op == UnaryOp::USub
                && matches!(&*node.operand, Expr::NumberLiteral(inner) if matches!(inner.value, Number::Int(_)))
        }
        _ => false,
    }
}

fn builtin(name: &str, text: String) -> TypeShape {
    if name == "object" {
        TypeShape::Dynamic {
            text,
            name: name.to_owned(),
        }
    } else {
        TypeShape::Primitive {
            text,
            name: name.to_owned(),
        }
    }
}

fn unreadable(text: String, cause: Unreadable) -> TypeShape {
    TypeShape::Unreadable { text, cause }
}

/// The import records of each module, by the name of the module.
pub(super) fn imports_by_module(
    imports: &[Record<ImportFact>],
) -> HashMap<&str, Vec<&Record<ImportFact>>> {
    let mut by_module: HashMap<&str, Vec<&Record<ImportFact>>> = HashMap::new();
    for record in imports {
        let source = ModuleName::as_str(&ImportFact::data(&record.data).source_module);
        by_module.entry(source).or_default().push(record);
    }
    by_module
}

/// The bindings that the written types of one module read.
pub(super) fn module_names<'a>(
    module: &'a Module,
    binders: &'a Binders,
    by_module: &HashMap<&str, Vec<&Record<ImportFact>>>,
    sets: (&HashSet<String>, &HashSet<String>),
) -> Names<'a> {
    let own = HashMap::get(by_module, String::as_str(&module.name));
    let records = own.map_or(&[][..], Vec::as_slice);
    Names::of((&module.name, &module.tree), binders, records, sets)
}

impl<'a> Shaper<'a> {
    /// The reader of the written types of `module`: on Python 3.14 a method annotation reads
    /// the class namespace, unless the module makes its annotations strings (#1523).
    pub(super) fn of(names: &'a Names<'a>, lazy: Option<&'a ClassWrites>, module: &Module) -> Self {
        let lazy = lazy.filter(|_| !future_annotations(&module.tree));
        Shaper { names, lazy }
    }
}

/// Write the shapes of the signature of each source of each module into its record. A record
/// whose parameters do not match the signature of its source gets none: the model then reads the
/// shapes as not written.
pub(crate) fn attach(
    found: &mut [Found<'_>],
    (modules, binders): (&[Module], &[Binders]),
    imports: &[Record<ImportFact>],
    sets: (&HashSet<String>, &HashSet<String>),
    lazy: Option<&ClassWrites>,
) {
    let by_module = imports_by_module(imports);
    for item in found {
        let module = &modules[item.index];
        let names = module_names(module, &binders[item.index], &by_module, sets);
        let shaper = Shaper::of(&names, lazy, module);
        let at: HashMap<&str, usize> = item
            .records
            .iter()
            .enumerate()
            .map(|(index, record)| (record.id.as_str(), index))
            .collect();
        let mut written = Vec::new();
        for source in &item.sources {
            if let Some(&index) = at.get(source.id.as_str()) {
                written.push((index, shaper.signature(source)));
            }
        }
        for (index, (shapes, returns)) in written {
            let (SymbolFact::Function(data) | SymbolFact::Method(data)) =
                &mut item.records[index].data
            else {
                continue;
            };
            if shapes.len() != data.parameters.len() {
                continue;
            }
            for (parameter, shape) in data.parameters.iter_mut().zip(shapes) {
                parameter.shape = Some(shape);
            }
            data.returns_shape = Some(returns);
        }
    }
}

#[cfg(test)]
#[path = "shapes_tests.rs"]
mod tests;

#[derive(Default)]
struct ClassWalk(bool);

impl<'a> Visitor<'a> for ClassWalk {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if matches!(stmt, Stmt::ClassDef(_)) {
            self.0 = true;
        } else {
            visitor::walk_stmt(self, stmt);
        }
    }
}

pub(super) fn no_nested_classes(body: &[Stmt]) -> bool {
    let mut walk = ClassWalk::default();
    walk.visit_body(body);
    !walk.0
}

// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The types as written in a signature, a field or a `let` (#1571, AD-804). Rust writes the type
//! of each parameter, field and return value, so the scan reads it as a path with its type
//! arguments, a reference, a slice or a tuple. A name of a type parameter in scope, `impl Trait`,
//! `dyn Trait`, a qualified or absolute path and a macro stay `Unknown`: the collector keeps
//! the gaps of a receiver of such a type. `Self` stays a path `Self`; the resolver
//! (`impl_types.rs`) gives it the type of the block.

use std::collections::BTreeSet;

use syn::{GenericArgument, GenericParam, Generics, PathArguments, ReturnType, Signature, Type};

use crate::definitions::{SelfKind, Written};
use crate::tokens::plain;

/// The names of the type and const parameters of an item.
pub(in crate::scan) fn generic_names(generics: &Generics) -> BTreeSet<String> {
    let names = generics.params.iter().filter_map(|param| match param {
        GenericParam::Type(found) => Some(plain(&found.ident)),
        GenericParam::Const(found) => Some(plain(&found.ident)),
        GenericParam::Lifetime(_) => None,
    });
    names.collect()
}

/// A type as written. `hidden` holds the type and const parameters in scope.
pub(in crate::scan) fn written(ty: &Type, hidden: &BTreeSet<String>) -> Written {
    match ty {
        Type::Reference(found) => {
            let kind = match found.mutability {
                Some(_) => SelfKind::Unique,
                None => SelfKind::Shared,
            };
            Written::Ref(kind, Box::new(written(&found.elem, hidden)))
        }
        Type::Slice(found) => Written::Slice(Box::new(written(&found.elem, hidden))),
        Type::Array(found) => Written::Slice(Box::new(written(&found.elem, hidden))),
        Type::Paren(found) => written(&found.elem, hidden),
        Type::Tuple(found) => {
            Written::Tuple(found.elems.iter().map(|ty| written(ty, hidden)).collect())
        }
        Type::Group(found) => written(&found.elem, hidden),
        Type::Path(found) if found.qself.is_none() && found.path.leading_colon.is_none() => {
            path_type(&found.path, hidden).unwrap_or(Written::Unknown)
        }
        _ => Written::Unknown,
    }
}

/// A relative type path with the type arguments of its last segment.
fn path_type(path: &syn::Path, hidden: &BTreeSet<String>) -> Option<Written> {
    let segments = &path.segments;
    let mut names = Vec::new();
    let mut args = Vec::new();
    for (at, segment) in segments.iter().enumerate() {
        match &segment.arguments {
            PathArguments::None => {}
            PathArguments::AngleBracketed(list) if at + 1 == segments.len() => {
                args = arguments(list, hidden)?;
            }
            _ => return None,
        }
        names.push(plain(&segment.ident));
    }
    names.first().filter(|first| !hidden.contains(*first))?;
    Some(Written::Path(names, args))
}

/// The type arguments of a segment, without lifetimes, or `None` for a const or an associated
/// type binding.
fn arguments(
    list: &syn::AngleBracketedGenericArguments,
    hidden: &BTreeSet<String>,
) -> Option<Vec<Written>> {
    let mut args = Vec::new();
    for argument in &list.args {
        match argument {
            GenericArgument::Lifetime(_) => {}
            GenericArgument::Type(ty) => args.push(written(ty, hidden)),
            _ => return None,
        }
    }
    Some(args)
}

/// The written return type of a `fn`. `outer` holds the type parameters of the enclosing block.
/// An `async fn` returns a future, so its type is `Unknown`, as is the unit type.
pub(in crate::scan) fn returned(sig: &Signature, outer: &BTreeSet<String>) -> Written {
    let ReturnType::Type(_, ty) = &sig.output else {
        return Written::Unknown;
    };
    if sig.asyncness.is_some() {
        return Written::Unknown;
    }
    let mut hidden = outer.clone();
    hidden.extend(generic_names(&sig.generics));
    written(ty, &hidden)
}

/// A type that the body or the signature of a `fn` writes, with `Self` replaced by the exact path
/// of the block, or `Unknown` when the block has none. A tuple keeps its elements.
pub(in crate::scan) fn with_self(ty: Written, self_type: Option<&[String]>) -> Written {
    match ty {
        Written::Path(names, args) if names.first().is_some_and(|first| first == "Self") => {
            match self_type {
                Some(path) if names.len() == 1 && args.is_empty() => {
                    Written::Path(path.to_vec(), Vec::new())
                }
                _ => Written::Unknown,
            }
        }
        Written::Path(names, args) => {
            let args = args.into_iter().map(|arg| with_self(arg, self_type));
            Written::Path(names, args.collect())
        }
        Written::Ref(kind, inner) => Written::Ref(kind, Box::new(with_self(*inner, self_type))),
        Written::Slice(inner) => Written::Slice(Box::new(with_self(*inner, self_type))),
        Written::Tuple(elems) => Written::Tuple(
            elems
                .into_iter()
                .map(|ty| with_self(ty, self_type))
                .collect(),
        ),
        Written::Unknown => Written::Unknown,
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use super::{returned, written};
    use crate::definitions::{SelfKind, Written};

    fn path(names: &[&str], args: Vec<Written>) -> Written {
        Written::Path(names.iter().map(|n| (*n).to_owned()).collect(), args)
    }

    #[test]
    fn a_written_type_keeps_its_arguments_and_drops_lifetimes() {
        let ty: syn::Type =
            syn::parse_str("&'a std::collections::BTreeMap<String, Vec<c::S>>").unwrap();
        let args = vec![
            path(&["String"], vec![]),
            path(&["Vec"], vec![path(&["c", "S"], vec![])]),
        ];
        let map = path(&["std", "collections", "BTreeMap"], args);
        assert_eq!(
            written(&ty, &BTreeSet::new()),
            Written::Ref(SelfKind::Shared, Box::new(map))
        );
    }

    #[test]
    fn a_type_parameter_impl_trait_and_async_are_unknown() {
        let hidden: BTreeSet<String> = ["T".to_owned()].into();
        let ty: syn::Type = syn::parse_str("Vec<T>").unwrap();
        assert_eq!(
            written(&ty, &hidden),
            path(&["Vec"], vec![Written::Unknown])
        );
        let item: syn::ItemFn = syn::parse_str("fn f<U>() -> U { todo!() }").unwrap();
        assert_eq!(returned(&item.sig, &BTreeSet::new()), Written::Unknown);
        let item: syn::ItemFn = syn::parse_str("fn f() -> impl Tr { todo!() }").unwrap();
        assert_eq!(returned(&item.sig, &BTreeSet::new()), Written::Unknown);
        let item: syn::ItemFn = syn::parse_str("async fn f() -> S { todo!() }").unwrap();
        assert_eq!(returned(&item.sig, &BTreeSet::new()), Written::Unknown);
        let ty: syn::Type = syn::parse_str("<S as Tr>::Out").unwrap();
        assert_eq!(written(&ty, &BTreeSet::new()), Written::Unknown);
    }
}

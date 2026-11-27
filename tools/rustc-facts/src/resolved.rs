// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A method call `x.m()` whose callee the compiler resolved (AD-1185).
//!
//! The record states a fact of the compiler for one call site: the operand types are concrete and the call goes
//! to one function. The site is the span of `m(..)` (`fn_span`), the place where the scan reads the method name.
//! A call with a type parameter, a trait object or a call that a macro wrote gives no record.

use crate::holders::holds_only_arguments;
use crate::items::absolute;
use crate::state::{ImplIndex, Resolved, State};
use rustc_hir::def::DefKind;
use rustc_hir::def_id::{DefId, LOCAL_CRATE};
use rustc_middle::ty::{self, GenericArgsRef, Ty, TyCtxt, TypeVisitableExt};
use rustc_span::{sym, FileName, Span};
use std::collections::BTreeSet;

/// The impls of the workspace by the self type that they name: an ADT, a type parameter (blanket) or another type.
fn impl_index(st: &mut State, tcx: TyCtxt<'_>) -> ImplIndex {
    let mut index = ImplIndex::default();
    let crates = std::iter::once(LOCAL_CRATE).chain(tcx.crates(()).iter().copied());
    for cnum in crates {
        let root = DefId {
            krate: cnum,
            index: rustc_hir::def_id::CRATE_DEF_INDEX,
        };
        if cnum != LOCAL_CRATE && !crate::body::inside(st, tcx, root) {
            continue;
        }
        for imp in tcx.trait_impls_in_crate(cnum) {
            let file = crate::items::file(tcx, st, *imp);
            match tcx.type_of(*imp).skip_binder().kind() {
                ty::Adt(def, _) => {
                    index.by_adt.entry(def.did()).or_default().insert(file);
                }
                ty::Param(_) => {
                    index.blanket.insert(file);
                }
                _ => {
                    index.other.insert(file);
                }
            }
        }
    }
    index
}

/// What the type arguments of a call can run (see `touch`).
struct Touched<'tcx> {
    files: BTreeSet<u32>,
    /// An argument is not fully known, or can hide code.
    open: bool,
    /// An argument is a plain type that is no ADT (a number, a reference, a tuple).
    plain: bool,
    /// The types that were visited, with their trust: a recursive type ends the walk. The type itself is the key,
    /// because two closures of one definition print the same text.
    seen: std::collections::HashSet<(Ty<'tcx>, bool)>,
    /// The first type that made the call open, for the facts.
    why: Option<String>,
}

impl Touched<'_> {
    fn open_by(&mut self, ty: &str) {
        self.open = true;
        self.why.get_or_insert_with(|| ty.to_owned());
    }
}

/// The most types that one call visits. A type that grows without end (`R<T>` holds `R<Vec<T>>`) is open.
const BUDGET: usize = 300;

/// Visit one type: its definition file, the files of its impls, and the types inside it. A closure shows its
/// captured types and the arguments of its parent, not its signature (a signature is a function pointer type).
/// `trusted` is true inside the field of an allowed type of the standard library (a container keeps raw
/// pointers to bytes, which hide no callback).
fn visit<'tcx>(
    st: &mut State,
    tcx: TyCtxt<'tcx>,
    env: ty::TypingEnv<'tcx>,
    ty: Ty<'tcx>,
    (found, trusted): (&mut Touched<'tcx>, bool),
) {
    // The key holds the trust: a type that was safe inside a container is not safe in a field of a user type.
    if !found.seen.insert((ty, trusted)) {
        return;
    }
    if found.seen.len() > BUDGET {
        found.open_by("<budget>");
        return;
    }
    let nested = |args: &[ty::GenericArg<'tcx>]| -> Vec<(Ty<'tcx>, bool)> {
        args.iter()
            .filter_map(|a| a.as_type())
            .map(|t| (t, false))
            .collect()
    };
    let inner: Vec<(Ty<'tcx>, bool)> = match *ty.kind() {
        ty::Adt(def, args) => {
            found.files.insert(crate::items::file(tcx, st, def.did()));
            for imp in tcx.inherent_impls(def.did()) {
                found.files.insert(crate::items::file(tcx, st, *imp));
            }
            let own = st.impls.as_ref().and_then(|i| i.by_adt.get(&def.did()));
            found.files.extend(own.into_iter().flatten().copied());
            let mut all = nested(&args[..]);
            // The fields of a type can hold callable state that no argument names (a function pointer, a trait
            // object, a closure, a type that an associated type names). The walk enters the fields of every type. A
            // type of the standard library must also be a container, a smart pointer, a cell, a range or an iterator
            // adapter; another one (`Waker`, `Formatter`) is open.
            let standard =
                [sym::core, sym::alloc, sym::std].contains(&tcx.crate_name(def.did().krate));
            let allowed = standard && holds_only_arguments(tcx, def.did());
            if standard && !allowed {
                found.open_by(&crate::names::path(tcx, def.did()));
            }
            // Only an owner of `alloc` (`Vec`, `Box`, `Rc`) or what it holds is trusted to keep bytes in raw
            // pointers. A pointer wrapper that a user type names (`NonNull<u8>`) can hide a callback.
            let allowed =
                allowed && (trusted || crate::names::path(tcx, def.did()).starts_with("alloc::"));
            for field in def.all_fields() {
                match tcx.try_normalize_erasing_regions(env, field.ty(tcx, args)) {
                    Ok(field_ty) => all.push((field_ty, allowed)),
                    Err(_) => found.open_by("<field>"),
                }
            }
            all
        }
        ty::Closure(d, args) => {
            found.files.insert(crate::items::file(tcx, st, d));
            let closure = args.as_closure();
            let mut all = nested(closure.parent_args());
            all.extend(closure.upvar_tys().iter().map(|t| (t, false)));
            all
        }
        ty::FnDef(d, args) => {
            found.files.insert(crate::items::file(tcx, st, d));
            nested(&args[..])
        }
        ty::Foreign(d) => {
            found.files.insert(crate::items::file(tcx, st, d));
            Vec::new()
        }
        // A pointer to `()`, `c_void`, an extern type or a number erases the type of its value: a callback can hide
        // behind it (AD-1047).
        // Inside an allowed container only a pointer to bytes is known (`Vec` keeps `*const u8`); a pointer to
        // `()` hides the type even there (`NonNull<()>`).
        ty::RawPtr(t, _)
            if crate::reach::erases(tcx, t)
                && !(trusted && matches!(t.kind(), ty::Uint(ty::UintTy::U8))) =>
        {
            found.open_by("<erased pointer>");
            Vec::new()
        }
        ty::Pat(t, _) | ty::Ref(_, t, _) | ty::RawPtr(t, _) | ty::Slice(t) | ty::Array(t, _) => {
            found.plain = true;
            vec![(t, trusted)]
        }
        ty::Tuple(items) => {
            found.plain = true;
            items.iter().map(|t| (t, trusted)).collect()
        }
        ty::Bool | ty::Char | ty::Int(_) | ty::Uint(_) | ty::Float(_) | ty::Str | ty::Never => {
            found.plain = true;
            Vec::new()
        }
        // Any other kind can carry code that the type does not name: a function pointer, a trait object, a
        // coroutine, a parameter, an alias. Nothing is proven.
        _ => {
            found.open_by(&ty.to_string());
            Vec::new()
        }
    };
    for (t, inside) in inner {
        visit(st, tcx, env, t, (found, inside));
    }
}

/// What the type arguments of a call can run: the files that hold the types, the closures and the impls of them.
/// `open` when an argument is not fully known (a trait object, a type parameter): then nothing is proven.
fn touch<'tcx>(
    st: &mut State,
    tcx: TyCtxt<'tcx>,
    env: ty::TypingEnv<'tcx>,
    calls: &[(DefId, GenericArgsRef<'tcx>)],
) -> (BTreeSet<u32>, Option<String>) {
    if st.impls.is_none() {
        let index = impl_index(st, tcx);
        st.impls = Some(index);
    }
    let mut found = Touched {
        files: BTreeSet::new(),
        open: false,
        plain: false,
        seen: std::collections::HashSet::new(),
        why: None,
    };
    // The values that each call can touch: its type arguments, the types of its inputs (the receiver of a method
    // without generics is no argument, but its fields can hold callable state) and of its output (the caller can
    // run what the call returns).
    for (callee, args) in calls {
        // A closure or a shim has no signature to read: it is unknown here.
        if !matches!(
            tcx.def_kind(*callee),
            DefKind::Fn | DefKind::AssocFn | DefKind::Ctor(..)
        ) {
            found.open_by("<callee>");
            continue;
        }
        let sig = tcx.fn_sig(*callee).instantiate(tcx, *args).skip_binder();
        let mut types: Vec<Ty<'tcx>> = sig.inputs().to_vec();
        types.push(sig.output());
        types.extend(args.iter().filter_map(|a| a.as_type()));
        for ty in types {
            let ty = tcx
                .try_normalize_erasing_regions(env, ty::Unnormalized::new(ty))
                .unwrap_or(ty);
            visit(st, tcx, env, ty, (&mut found, false));
        }
    }
    if let Some(index) = st.impls.as_ref() {
        found.files.extend(index.blanket.iter().copied());
        if found.plain {
            found.files.extend(index.other.iter().copied());
        }
    }
    (found.files, found.why)
}

/// The function that a call goes to, and the arguments of its instance, or `None` when the compiler does not
/// resolve it to one function with concrete types.
fn resolve<'tcx>(
    tcx: TyCtxt<'tcx>,
    env: ty::TypingEnv<'tcx>,
    (def, args): (DefId, GenericArgsRef<'tcx>),
) -> Option<(DefId, GenericArgsRef<'tcx>)> {
    if tcx.trait_of_assoc(def).is_none() {
        return Some((def, args));
    }
    if args.has_param() || args.has_infer() {
        return None;
    }
    let Ok(Some(instance)) = ty::Instance::try_resolve(tcx, env, def, args) else {
        return None;
    };
    let ty::InstanceKind::Item(selected) = instance.def else {
        return None;
    };
    (!instance.args.has_param()).then_some((selected, instance.args))
}

/// The place of `fn_span` as the file id and the position, when it is a real file of the workspace.
fn place(st: &mut State, tcx: TyCtxt<'_>, fn_span: Span) -> Option<(u32, u32, u32)> {
    let start = tcx.sess.source_map().lookup_char_pos(fn_span.lo());
    if !matches!(start.file.name, FileName::Real(_)) {
        return None;
    }
    let path = absolute(&start.file.name.prefer_local_unconditionally().to_string());
    let rel = path.strip_prefix(&st.root)?.to_string();
    let line = u32::try_from(start.line).unwrap_or(u32::MAX);
    Some((
        st.names.text(&rel),
        line,
        u32::try_from(start.col.0).unwrap_or(u32::MAX),
    ))
}

/// A record for a place whose callee is not known: it is open, so it only vetoes.
fn unresolved(st: &mut State, tcx: TyCtxt<'_>, caller: u32, fn_span: Span) {
    let Some((file, line, column)) = place(st, tcx, fn_span) else {
        return;
    };
    let callee = st.names.text("<unresolved>");
    st.calls.insert(Resolved {
        from: caller,
        to: None,
        callee,
        file,
        callee_file: None,
        touch: BTreeSet::new(),
        open: Some(st.names.text("<unresolved>")),
        line,
        column,
    });
}

/// Add a record when `func_ty` is a method call that the compiler resolves to one function. `owner` is the root
/// of the body that makes the call, `caller` the id of its module. `span` is the whole call, `fn_span` its `m(..)`.
pub(crate) fn method_site<'tcx>(
    st: &mut State,
    tcx: TyCtxt<'tcx>,
    (owner, caller): (DefId, u32),
    func_ty: Ty<'tcx>,
    (span, fn_span): (Span, Span),
    siblings: &[(Span, Ty<'tcx>)],
) {
    // A path call `T::m(..)` starts where its function starts: only a dot call has a receiver before `m`.
    if fn_span.from_expansion() || fn_span.lo() == span.lo() {
        return;
    }
    let ty::FnDef(def, args) = *func_ty.kind() else {
        return;
    };
    let trait_of = tcx.trait_of_assoc(def);
    if trait_of.is_some() && trait_of == tcx.lang_items().eq_trait() {
        return;
    }
    let env = ty::TypingEnv::post_analysis(tcx, owner);
    let args = tcx.erase_and_anonymize_regions(args);
    let resolved = resolve(tcx, env, (def, args));
    let Some((callee, instance_args)) = resolved else {
        // A call that is not resolved here (a trait object, a type parameter) still marks its place: another unit
        // of the same place cannot then decide alone (AD-1185).
        unresolved(st, tcx, caller, fn_span);
        return;
    };
    // The calls inside the receiver and the arguments belong to the site: `make()`, and the `Deref` that an
    // adjustment adds. A call there that is not resolved opens the site.
    let mut calls = vec![(callee, instance_args)];
    let mut unknown = false;
    for (other, other_ty) in siblings {
        // The receiver and the arguments, with the adjustments (`Deref`) that coerce them.
        let inside = span.lo() <= other.lo() && other.hi() <= span.hi() && *other != span;
        let ty::FnDef(d, a) = *other_ty.kind() else {
            unknown |= inside;
            continue;
        };
        if !inside {
            continue;
        }
        match resolve(tcx, env, (d, tcx.erase_and_anonymize_regions(a))) {
            Some(found) => calls.push(found),
            None => unknown = true,
        }
    }
    let (touch, why) = touch(st, tcx, env, &calls);
    let why = why.or_else(|| unknown.then(|| "<operand>".to_owned()));
    let why = why.map(|text| st.names.text(&text));
    let Some((file, line, column)) = place(st, tcx, fn_span) else {
        return;
    };
    let callee_id = st.names.def(tcx, callee);
    let inside = crate::body::inside(st, tcx, callee);
    let to = inside.then(|| {
        let module = crate::selected::module_of(tcx, callee);
        st.names.def(tcx, module)
    });
    let callee_file = inside.then(|| crate::items::file(tcx, st, callee));
    st.calls.insert(Resolved {
        from: caller,
        to,
        callee: callee_id,
        file,
        callee_file,
        touch,
        open: why,
        line,
        column,
    });
}

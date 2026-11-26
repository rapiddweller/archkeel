// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The walk over one MIR body: types of locals, calls, casts and constants (AD-1047).

use crate::bounds::bounded_params;
use crate::reach::{scan, Found};
use crate::state::{Coerced, Flow, GenericFn, Hidden, Module, State};
use rustc_hir::def_id::{DefId, LocalDefId, LOCAL_CRATE};
use rustc_middle::mir::visit::Visitor;
use rustc_middle::mir::{
    Body, CastKind, ConstOperand, Local, LocalDecl, Location, Rvalue, Terminator, TerminatorKind,
};
use rustc_middle::ty::adjustment::PointerCoercion;
use rustc_middle::ty::{self, TyCtxt};
use std::collections::BTreeSet;

struct Walk<'a, 'tcx> {
    tcx: TyCtxt<'tcx>,
    body: &'a Body<'tcx>,
    st: &'a mut State,
    module: u32,
    me: u32,
    root: DefId,
    generic: bool,
    /// What this body mentions: the hidden types of its future when it is a coroutine.
    hidden: Hidden,
}

fn type_params(tcx: TyCtxt<'_>, d: DefId) -> usize {
    let g = tcx.generics_of(d);
    g.own_counts().types
        + g.parent
            .map_or(0, |p| tcx.generics_of(p).own_counts().types)
}

/// A callee counts when its source is in the workspace, or when it is a trait item: a trait item of
/// any crate can have an implementation in the workspace.
fn counts(st: &mut State, tcx: TyCtxt<'_>, d: DefId) -> bool {
    tcx.trait_of_assoc(d).is_some() || inside(st, tcx, d)
}

/// The definition is workspace code: its crate is the one that the driver compiles, or a crate whose own run of
/// the driver was a verified member (its manifest directory and root file are those of one member). The crate id
/// decides, no name and no path: a path dependency that is no member has no run and is foreign.
pub(crate) fn inside(st: &mut State, tcx: TyCtxt<'_>, d: DefId) -> bool {
    if d.krate == LOCAL_CRATE {
        return true;
    }
    if let Some(known) = st.workspace_defs.get(&d) {
        return *known;
    }
    let id = tcx.stable_crate_id(d.krate).as_u64();
    let inside = std::path::Path::new(&format!("{}/{id:016x}", st.registry)).is_file();
    st.workspace_defs.insert(d, inside);
    inside
}

impl<'a, 'tcx> Walk<'a, 'tcx> {
    fn found(&mut self, ty: ty::Ty<'tcx>) -> Found {
        let mut f = Found::new();
        scan(self.tcx, &mut self.st.names, ty, &mut f);
        f
    }

    fn mention(&mut self, ty: ty::Ty<'tcx>) {
        let f = self.found(ty);
        self.add(f, false);
    }

    /// Fold a finding into the module. `dyn_in` marks the dyn traits of a call as inputs or outputs.
    fn add(&mut self, f: Found, dyn_in: bool) {
        for d in &f.opaques {
            self.st.opaque_defs.insert(*d);
        }
        let opaque_ids: Vec<u32> = f
            .opaques
            .iter()
            .map(|d| self.st.names.def(self.tcx, *d))
            .collect();
        self.hidden.adts.extend(f.adts.iter().copied());
        self.hidden.dyns.extend(f.dyns.iter().copied());
        self.hidden.opaques.extend(opaque_ids.iter().copied());
        let m = self.st.modules.get_mut(&self.module);
        let Some(m) = m else { return };
        m.erased |= f.erased;
        m.mentions.extend(f.adts);
        m.opaques.extend(opaque_ids);
        if dyn_in {
            m.dyn_in.extend(f.dyns.iter().copied());
        }
        m.dyns.extend(f.dyns);
    }

    fn call(&mut self, func_ty: ty::Ty<'tcx>) {
        self.mention(func_ty);
        let ty::FnDef(def, args) = *func_ty.kind() else {
            return;
        };
        let sig = self
            .tcx
            .fn_sig(def)
            .instantiate(self.tcx, args)
            .skip_binder();
        for t in sig.inputs_and_output.iter() {
            self.mention(t);
        }
        let out = self.found(sig.output());
        self.add(
            Found {
                dyns: out.dyns,
                ..Found::new()
            },
            true,
        );
        self.callee(def, args);
    }

    /// The ADTs and `dyn` traits in the type arguments `args`; with `only`, in the bounded ones.
    fn type_args(&mut self, args: ty::GenericArgsRef<'tcx>, only: Option<&[bool]>) -> Found {
        let mut found = Found::new();
        for (at, g) in args.iter().enumerate() {
            let kept = only.is_none_or(|b| b.get(at).copied().unwrap_or(true));
            if let (true, Some(t)) = (kept, g.as_type()) {
                scan(self.tcx, &mut self.st.names, t, &mut found);
            }
        }
        found
    }

    /// A call, or a function used as a value (`FnDef` operand, `ReifyFnPointer`): the type arguments flow
    /// into the callee. A callee outside the workspace, or an item of a trait outside the workspace (its
    /// impl can be there), is also the `<foreign>` target: its code is not in the MIR of the workspace, so
    /// a type that reaches it can be coerced there (hole H2), but only through a parameter that it bounds.
    fn callee(&mut self, def: DefId, args: ty::GenericArgsRef<'tcx>) {
        if type_params(self.tcx, def) == 0 {
            return;
        }
        let trait_item = self.tcx.trait_of_assoc(def);
        let outside = match trait_item {
            Some(t) => !inside(self.st, self.tcx, t),
            None => !inside(self.st, self.tcx, def),
        };
        if counts(self.st, self.tcx, def) {
            let to = self.st.names.def(self.tcx, def);
            let all = self.type_args(args, None);
            self.flow(to, &all);
        }
        if outside {
            let to = self.st.names.text("<foreign>");
            let bounded = bounded_params(self.tcx, def);
            let some = self.type_args(args, Some(&bounded));
            self.flow(to, &some);
            self.via(def, args, &some);
        }
    }

    /// Record which signatures the escaped types met: a type that a call outside the workspace takes can be
    /// hidden in an ADT of that signature, or behind a raw pointer to `()` in it.
    fn via(&mut self, def: DefId, args: ty::GenericArgsRef<'tcx>, escaped: &Found) {
        if escaped.is_empty() {
            return;
        }
        let sig = self
            .tcx
            .fn_sig(def)
            .instantiate(self.tcx, args)
            .skip_binder();
        let mut met = Found::new();
        for t in sig.inputs_and_output.iter() {
            scan(self.tcx, &mut self.st.names, t, &mut met);
        }
        let mut keys: Vec<u32> = met.adts.iter().copied().collect();
        if met.erased {
            keys.push(self.st.names.text("<ptr>"));
        }
        let opaques = self.opaque_names(&escaped.opaques);
        for key in keys {
            let flow = self.st.via.entry(key).or_default();
            flow.adts.extend(escaped.adts.iter().copied());
            flow.adts.extend(opaques.iter().copied());
            flow.dyns.extend(escaped.dyns.iter().copied());
        }
    }

    fn flow(&mut self, to: u32, type_args: &Found) {
        // An opaque type or a coroutine flows by its name: the reader expands it to its hidden types.
        let opaques = self.opaque_names(&type_args.opaques);
        let flow: &mut Flow = if self.generic {
            self.st.edges.entry((self.me, to)).or_default()
        } else if type_args.is_empty() {
            return;
        } else {
            self.st.seeds.entry(to).or_default()
        };
        flow.adts.extend(type_args.adts.iter().copied());
        flow.adts.extend(opaques);
        flow.dyns.extend(type_args.dyns.iter().copied());
        flow.param |= type_args.param;
    }

    fn opaque_names(&mut self, defs: &[DefId]) -> Vec<u32> {
        defs.iter()
            .map(|d| {
                self.st.opaque_defs.insert(*d);
                self.st.names.def(self.tcx, *d)
            })
            .collect()
    }

    /// The destructor of each ADT in a dropped type runs for the type arguments of that ADT: an edge to it.
    fn destructors(&mut self, ty: ty::Ty<'tcx>) {
        for arg in ty.walk() {
            let Some(t) = arg.as_type() else { continue };
            let ty::Adt(def, args) = *t.kind() else {
                continue;
            };
            let Some(destructor) = self.tcx.adt_destructor(def.did()) else {
                continue;
            };
            self.callee(destructor.did, args);
        }
    }

    fn fn_value(&mut self, ty: ty::Ty<'tcx>) {
        let ty::FnDef(def, args) = *ty.kind() else {
            return;
        };
        self.callee(def, args);
    }

    /// A pointer cast, a transmute or an address cast can give a value a type that does not name it: the ADTs
    /// of the source that the target does not name are behind an erased value.
    fn erasing_cast(&mut self, kind: &CastKind, from: ty::Ty<'tcx>, to: ty::Ty<'tcx>) {
        let moves = matches!(
            kind,
            CastKind::PtrToPtr
                | CastKind::Transmute
                | CastKind::FnPtrToPtr
                | CastKind::PointerExposeProvenance
                | CastKind::PointerWithExposedProvenance
        );
        if !moves {
            return;
        }
        let (src, tgt) = (self.found(from), self.found(to));
        let lost: Vec<u32> = src.adts.difference(&tgt.adts).copied().collect();
        let lost_dyns: Vec<u32> = src.dyns.difference(&tgt.dyns).copied().collect();
        self.st.cast_lost.adts.extend(lost);
        self.st.cast_lost.dyns.extend(lost_dyns);
    }

    fn unsize(&mut self, from: ty::Ty<'tcx>, to: ty::Ty<'tcx>) {
        let src = self.found(from);
        let tgt = self.found(to);
        for tr in &tgt.dyns {
            // A site whose `dyn Fn*` signature is not written in full names the plain trait (AD-1160).
            let site = self.st.names.fn_site.get(tr).unwrap_or(tr);
            let c = self.st.coerce.entry(*site).or_insert_with(|| Coerced {
                adts: BTreeSet::new(),
                dyns: BTreeSet::new(),
                param_in: BTreeSet::new(),
                opaques: BTreeSet::new(),
            });
            c.adts.extend(src.adts.iter().copied());
            // A cast from a `dyn` to the same `dyn` (an auto trait or a lifetime changes) holds no new value.
            c.dyns.extend(src.dyns.iter().copied().filter(|d| d != tr));
            if src.param {
                c.param_in.insert(self.me);
            }
            for d in &src.opaques {
                c.opaques.insert(self.st.names.def(self.tcx, *d));
            }
        }
        self.add(src, false);
        self.add(tgt, false);
    }
}

impl<'a, 'tcx> Visitor<'tcx> for Walk<'a, 'tcx> {
    fn visit_local_decl(&mut self, _l: Local, d: &LocalDecl<'tcx>) {
        self.mention(d.ty);
    }

    fn visit_const_operand(&mut self, c: &ConstOperand<'tcx>, _l: Location) {
        self.mention(c.const_.ty());
        self.fn_value(c.const_.ty());
    }

    fn visit_terminator(&mut self, t: &Terminator<'tcx>, l: Location) {
        match &t.kind {
            TerminatorKind::Call { func, .. } => {
                let fty = func.ty(&self.body.local_decls, self.tcx);
                self.call(fty);
                let at = (self.root, self.module);
                crate::selected::eq_site(self.st, self.tcx, at, fty, t.source_info.span);
            }
            // The glue of a drop runs the destructors of the type, also of a generic ADT.
            TerminatorKind::Drop { place, .. } => {
                let ty = place.ty(&self.body.local_decls, self.tcx).ty;
                self.mention(ty);
                self.destructors(ty);
            }
            _ => {}
        }
        self.super_terminator(t, l);
    }

    fn visit_rvalue(&mut self, r: &Rvalue<'tcx>, l: Location) {
        if let Rvalue::Cast(kind, op, to) = r {
            let from = op.ty(&self.body.local_decls, self.tcx);
            if matches!(kind, CastKind::PointerCoercion(PointerCoercion::Unsize, _)) {
                self.unsize(from, *to);
            } else {
                self.mention(from);
                self.mention(*to);
                self.erasing_cast(kind, from, *to);
            }
        }
        self.super_rvalue(r, l);
    }
}

/// Take the facts of one body. The compiler calls this when the query `mir_built` makes the MIR.
pub(crate) fn visit<'tcx>(st: &mut State, tcx: TyCtxt<'tcx>, d: LocalDefId, body: &Body<'tcx>) {
    let did = d.to_def_id();
    let module_def = tcx.parent_module_from_def_id(d).to_def_id();
    let module = st.names.def(tcx, module_def);
    let file = crate::items::file(tcx, st, module_def);
    st.modules.entry(module).or_insert_with(|| Module {
        file,
        mentions: BTreeSet::new(),
        dyns: BTreeSet::new(),
        opaques: BTreeSet::new(),
        dyn_in: BTreeSet::new(),
        erased: false,
    });
    // A closure has the generics and the instances of the function that owns it, so its facts
    // belong to that function. This keeps the file small.
    let root = tcx.typeck_root_def_id(did);
    let me = st.names.def(tcx, root);
    let generic = type_params(tcx, root) > 0;
    let mut w = Walk {
        tcx,
        body,
        st: &mut *st,
        module,
        me,
        root,
        generic,
        hidden: Hidden {
            adts: BTreeSet::new(),
            dyns: BTreeSet::new(),
            opaques: BTreeSet::new(),
        },
    };
    w.visit_body(body);
    for l in body.args_iter() {
        let ty = body.local_decls[l].ty;
        let f = w.found(ty);
        w.add(
            Found {
                dyns: f.dyns,
                ..Found::new()
            },
            true,
        );
    }
    let hidden = w.hidden;
    if tcx.is_coroutine(did) {
        let id = st.names.def(tcx, did);
        let seen = st.coroutines.entry(id).or_insert(Hidden {
            adts: BTreeSet::new(),
            dyns: BTreeSet::new(),
            opaques: BTreeSet::new(),
        });
        seen.adts.extend(hidden.adts);
        seen.dyns.extend(hidden.dyns);
        seen.opaques.extend(hidden.opaques);
    }
    if generic && !st.fns.contains_key(&me) {
        let implements = tcx
            .opt_associated_item(root)
            .and_then(|i| i.trait_item_def_id())
            .map(|t| st.names.def(tcx, t));
        st.fns.insert(me, GenericFn { module, implements });
    }
}

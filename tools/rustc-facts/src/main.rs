// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The rustc driver of ArchKeel: it compiles one Cargo unit and writes its type-reach facts (AD-1047).
//!
//! Cargo calls it as `RUSTC_WORKSPACE_WRAPPER`: the first argument is the path of `rustc`. The driver
//! takes the facts when rustc builds the MIR of each body, so macro and derive output is in it.
//! The collector gives the binding through the environment: `AK_FACTS_DIR`, `AK_FACTS_CFG`,
//! `AK_FACTS_DRIVER_SHA256`, `AK_FACTS_LOCK_SHA256` and `AK_FACTS_ROOT`.

#![feature(rustc_private)]
extern crate rustc_data_structures;
extern crate rustc_driver;
extern crate rustc_hir;
extern crate rustc_interface;
extern crate rustc_middle;
extern crate rustc_span;

mod body;
mod bounds;
mod items;
mod json;
mod names;
mod out;
mod reach;
mod state;

use rustc_data_structures::steal::Steal;
use rustc_driver::Compilation;
use rustc_hir::def::DefKind;
use rustc_hir::def_id::LocalDefId;
use rustc_interface::interface::Compiler;
use rustc_middle::mir::Body;
use rustc_middle::ty::TyCtxt;
use std::sync::OnceLock;

type MirBuilt = for<'tcx> fn(TyCtxt<'tcx>, LocalDefId) -> &'tcx Steal<Body<'tcx>>;

static ORIGINAL: OnceLock<MirBuilt> = OnceLock::new();

/// `mir_built` is the MIR before borrowck and optimization. Later passes steal it, so the facts are
/// taken here, when the query makes it. Reading it after expansion panics.
fn mir_built_hook<'tcx>(tcx: TyCtxt<'tcx>, d: LocalDefId) -> &'tcx Steal<Body<'tcx>> {
    let original = ORIGINAL
        .get()
        .expect("config sets the provider before any query");
    let steal = original(tcx, d);
    {
        let guard = steal.borrow();
        let body: &Body<'tcx> = &guard;
        body::visit(&mut state::lock(), tcx, d, body);
    }
    steal
}

struct Driver {
    unit: out::Unit,
}

impl rustc_driver::Callbacks for Driver {
    fn config(&mut self, config: &mut rustc_interface::interface::Config) {
        config.override_queries = Some(|_s, p| {
            let _ = ORIGINAL.set(p.queries.mir_built);
            p.queries.mir_built = mir_built_hook;
        });
    }

    fn after_analysis<'tcx>(&mut self, _c: &Compiler, tcx: TyCtxt<'tcx>) -> Compilation {
        // A verified member tells the later runs that its crate id is workspace code. Cargo starts a dependent
        // only when the metadata of its dependency is there, and that comes after this callback.
        let id = tcx.stable_crate_id(rustc_hir::def_id::LOCAL_CRATE).as_u64();
        let _ = std::fs::write(format!("{}/{id:016x}", state::lock().registry), "");
        // A forced query is cached, so a body that analysis skipped is also covered.
        for d in tcx.hir_body_owners() {
            let covered = matches!(
                tcx.def_kind(d),
                DefKind::Fn
                    | DefKind::AssocFn
                    | DefKind::Closure
                    | DefKind::Const { .. }
                    | DefKind::Static { .. }
                    | DefKind::AssocConst { .. }
            );
            if covered {
                let _ = tcx.mir_built(d);
            }
        }
        out::write(&self.unit, tcx, &mut state::lock());
        Compilation::Continue
    }
}

fn main() {
    let mut args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("archkeel-rustc-facts: Cargo gives the path of rustc as the first argument");
        std::process::exit(2);
    }
    let rustc = args.remove(1);
    let probe = args
        .iter()
        .any(|a| a == "-vV" || a == "--print" || a.starts_with("--print="));
    if probe || args.iter().any(|a| a.contains("build_script_build")) {
        let mut plain = rustc_driver::TimePassesCallbacks::default();
        rustc_driver::run_compiler(&args, &mut plain);
        return;
    }
    let Some(unit) = out::Unit::new(&rustc, &args) else {
        eprintln!("archkeel-rustc-facts: the environment is incomplete");
        std::process::exit(2);
    };
    // The sysroot is the one of the `rustc` that Cargo chose.
    if !args.iter().any(|a| a.starts_with("--sysroot")) {
        args.push(format!("--sysroot={}", out::sysroot(&rustc)));
    }
    // The file hash must be SHA-256. The flag is unstable, so only this process gets RUSTC_BOOTSTRAP.
    std::env::set_var("RUSTC_BOOTSTRAP", "1");
    args.push("-Zsrc-hash-algorithm=sha256".to_string());
    // A source file outside the root would get an absolute path that no scan path can match.
    let main_file = args
        .iter()
        .find(|a| !a.starts_with('-') && a.ends_with(".rs"));
    if let Some(file) = main_file
        .map(|f| items::absolute(f))
        .filter(|f| !f.starts_with(&unit.root))
    {
        eprintln!(
            "archkeel-rustc-facts: the source {file} is outside the scan root {}",
            unit.root
        );
        std::process::exit(2);
    }
    // The wrapper runs for workspace members only. A run that is no verified member makes no facts.
    let verified = main_file.is_some_and(|file| unit.is_member(file));
    if !verified {
        eprintln!("archkeel-rustc-facts: this crate is no workspace member of the producer");
        std::process::exit(2);
    }
    {
        let mut state = state::lock();
        state.root = unit.root.clone();
        state.registry = unit.registry.clone();
    }
    rustc_driver::run_compiler(&args, &mut Driver { unit });
}

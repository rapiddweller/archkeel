# Shared parameter-kind implementation plan

Base: e99394254846318e236ba471a14c19cd160081cf. Scope: #542 parser/protocol controls.

1. Commit this independently authored plan, Target and tests without production changes. Observe the missing Facts owner and raw producer signature as real RED.
2. Move the existing six-member enum unchanged from architecture_graph to facts, retain explicit identity reexport, annotate the actual private producer and use nominal members at its five writers. Expected net source under20 lines; no new owner layer or framework.
3. Route facts.py through required Report CI in the same change; preserve other routes and add its classifier case. Reproduce Graph assets; the canonical owner comments move to Facts while every runtime token remains identical.
4. Verify nominal producer values and exact serialized records, legacy Graph imports/construction, actual native Target PASS and actual source widening FAIL. Keep the Facts whole-module guard, with no new whole-symbols absence claim.
5. Run affected source/Graph/native regression, normal validation/receipt/replay, precise call/type/UNKNOWN and full fixture wire comparison; independent final Astra and actual-Main required CI before merge.

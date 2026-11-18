# AD-900: A proven execution pair does not hide a named use

Status: proposed. Part of #880. Builds on AD-898.

## Context

The named interface reads names and publication routes. It still reads the type
and route of a proved method receiver. AD-806 also records possible impl execution
without a named use. The old dispatch flag includes both this cause and the
unresolved named receivers of AD-804. The first cited site cannot separate them.

## Decision

- Before pair deduplication, check every pending named candidate for the pair.
  Mark a pair `RuntimeEffects` only when the candidates leave execution alone
  unknown. An earlier unclassified gap or a mixed pair does not get the mark.
- Both producer paths write the same records. The store checks the witness of
  the marked pair under the named-route policy. Its evidence cites the impl,
  not a caller or a proved invocation.
- Only the interface receipt releases a marked pair with a live dispatch fact,
  observed ends, and distinct or shared known owners. The named-site inventory
  of AD-898 stays open. Other rules still need the execution gap.

## Limits

- An archived reply does not carry the live dispatch fact. A worker without
  the complete marker and dispatch fact does not release the pair.
- A store that only accepts the earlier record form rejects a new marked pair.
  The separate process must negotiate the new evidence before using it.
- The marker is not proof that an impl did or did not execute. A proved receiver
  or a first cited derive does not discharge any of the other execution causes.

## Result

On the same native source tree, 22,904 pairs hold the interface before this
change and 1,384 hold it after. The verdict stays UNKNOWN. The other rule
readings and all 22,597 coverage gap records stay the same.

## Tests

The Cargo cases cover execution only, an unlisted name and a mixed pair.
The collector unit test reverses the causes and keeps every mixed pair open.
The model unit test keeps the gap relevant to other rule readings.

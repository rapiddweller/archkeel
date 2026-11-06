# AD-309 Native TypeScript uses compressed protocol 8

**Decision.** The default TypeScript collector requests protocol 8. The TypeScript entry echoes
the request version. The process boundary checks for a different reply version only when the
collector has an explicitly selected protocol version.

An explicit collector command keeps its selected request version. Its TypeScript entry therefore
keeps the V3 plain response; external collectors may also return another valid response version,
as before. Python and Dart keep their current protocol paths. The shared decoder remains the trust
boundary for response validation, compressed-byte limits, decompression limits and damaged frames.

**Reason.** TypeScript facts use the existing JSON envelope. Protocol 8 compresses that envelope
with the bounded codec. Incremental JSON encoding avoids a full JSON string and byte copy. The
existing `0x78` zlib header remains the wire marker ([wire vocabulary](../collector-wire-vocabulary.md),
[AD-259](ad-259-one-plain-wire-one-validation.md)).

**Measurement.** Three separate-process pairs used the public TypeScript fixture and 30,000
synthetic 1 KiB evidence entries. Both variants decoded to the same facts and plain JSON digest.
The 33,718,698 byte JSON used 18,319,289 wire bytes. Median peak RSS fell from 225 MiB to 124 MiB.
Median encode time rose from 0.257 s to 0.450 s. This measures the fixture and encoder only.

**Limit.** A separate Platform scan stopped at the 1.5 GiB RSS guard. Its 2.8 GiB sampled peak
does not identify the phase that used memory. This change does not claim to solve that scan.

The current contract and call-budget changes are bound by the [CI amendment](ad-309-v8-contract-amendment.json).

**Check.** The public TypeScript fixture produced 5,625 V8 bytes and 28,654 V3 bytes locally; both
decode to the same facts. Its Explore catalog row succeeds under an 8 KiB limit, and the V3
comparison exceeds that limit. These sizes describe this fixture, not a general ratio. Process
tests reject version mismatch. Codec tests cover damaged and oversized frames and preserve the
16x decompression bound.

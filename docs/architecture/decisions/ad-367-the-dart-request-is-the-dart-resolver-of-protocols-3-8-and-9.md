# AD-367 The Dart request is the Dart resolver of protocols 3, 8 and 9

**Status.** Accepted. Epic #880, PR 8 slice 2. It follows AD-365 and keeps AD-334.

**Decision.**
1. `Resolver` in `archkeel-facts` gets the variant `dart` with `DartSettings {}`, the
   `{"language": "dart"}` that `ir/protocol.DartSettings` writes. `Request::dart()` and
   `archkeel_wire::request::decode_dart` give a `DartRequest`.
2. The Dart resolver is valid with protocol 3.0.0, 8.0.0 and 9.0.0, the versions that the host
   sends for Dart. The rule of AD-334 stays: protocol 10.0.0 requires the Python resolver.
3. No protocol version changes. The host already writes this request; only the native reader
   learns it. The request schema `archkeel-request.schema.json` is generated again and gains
   the variant. The reply schema `archkeel-facts.schema.json` stays byte-equal.
4. The Dart binary decodes the request on stdin. A valid request gives exit code 2 and no reply
   until slice 5 of #880; a request that is not valid gives exit code 1 with the decode error.
5. No PASS: the host keeps the Python Dart collector, also when a native Dart binary and its
   digest are in the native directory, and the wheel does not carry the binary (AD-344).

**Problem.** The native Dart collector cannot read a request without a Dart resolver in the one
typed definition of the wire (AD-345). Protocol 10.0.0 added only the Python resolver.

**Rejected.** (a) A new protocol version: the request bytes of the host do not change. (b) Dart
settings in the collector crate: AD-345 gives each wire type one definition.

**Limit.** The schema test of the request names a new protocol version for a request change.
This change widens only what the native reader accepts, so it keeps the version.

**Tests.** `native/wire/src/request_tests.rs`, `tests/test_collector_native_dart_discovery.py`
(the request of the Python encoder decodes; the host never launches the native binary).

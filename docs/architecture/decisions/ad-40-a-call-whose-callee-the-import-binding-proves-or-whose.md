# AD-40 A call whose callee the import binding proves, or whose receiver is already typed, types its result from a documented table

Resolve call results through a closed constructor/method table only when import bindings prove the
type. Follow results forward within the owning scope; later rebinding does not erase an earlier
result. Unlisted calls stop resolution.

This supplies partial static evidence, not project-wide type inference or runtime behavior. Proof:
[test_analyzer.py](../../../tests/test_analyzer.py).

The closed constructor and receiver tables include selected `subprocess.Popen`, `threading.Thread`
and `threading.Event` APIs when imports prove their qualified identities. Generic Popen annotations
are limited to `Popen[bytes]` with the builtin unshadowed.
Import-bound `base64.b64encode`, `base64.urlsafe_b64encode`, `hmac.digest` and
`secrets.token_bytes` document a `bytes` result; downstream method calls remain partial.
Import-bound `hmac.new` documents an `hmac.HMAC` result, whose `digest` method documents
`bytes`; the following `bytes.hex` call remains partial.

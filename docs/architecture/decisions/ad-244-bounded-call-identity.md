# AD-244: Call identity admits bounded receiver and native proofs

Extend AD-241's `CallBinding` with typed origins for a uniquely stored annotated
field, a stable default construction, its constructor call, and selected native
stdlib APIs. Each binding keeps the same canonical target and evidence-ID shape.
Call candidates remain hints; only the binding proof can decide `call_owner`.

Stored fields are admitted when one plain initializer copies one typed parameter
to one `self.field`, the owner and type resolve uniquely, and no competing write,
delete, descriptor, or dynamic attribute hook is observed. Construction is
admitted for one stable imported or local class with a proved default instance
result. Inheritance follows a unique, source-resolved single-base chain and names
the defining method. Ambiguous bases and inherited overrides remain UNKNOWN.

The native witness is a stable, unshadowed import binding to one of these
canonical CPython standard-library identities: `random.random`, `random.Random`
and its listed `Random` methods, `datetime.datetime.now`, and `secrets.token_hex`.
Random and secrets identities are tied to exact captured provider member
declarations and their source digests. The datetime witness inspects the
collector's isolated Python runtime using `inspect.getattr_static` to observe
`datetime.datetime.__dict__["now"]` as the built-in class-method descriptor with
the canonical owner and member names; it also binds the stdlib source digest and
runtime implementation/version. This admits only the observed CPython descriptor
and does not import project modules. Other external APIs remain UNKNOWN until
they have an explicit provider-source or native witness.

Only `direct` and `declared_receiver` origins are valid in observation 2.1.
Extended origins require the declared `extended_call_bindings` capability and
observation 2.2. Saved readers reject those origins under 2.1. This consistency
binding does not authenticate a modified artifact or prove runtime dispatch.
There is no general runtime type inference, dynamic dispatch, custom allocation,
arbitrary descriptor, or arbitrary MRO support.

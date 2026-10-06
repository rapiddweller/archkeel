# AD-131: Public API closure includes inherited fields

Include public inherited fields in `public_api` through one local base chain.
Resolve annotations in their defining modules, using existing alias and generic
substitution proofs. Subclass members override inherited fields; entry origins exclude
expanded fields. Component publication does not declare the external API.

Private fields, implementation methods and framework bases do not enlarge the surface.
Multiple-base order, cycles, dynamic bodies and unsupported substitutions remain UNKNOWN;
runtime model behavior is unproved.

[Public API proof](../../../tests/test_public_api_boundary.py).

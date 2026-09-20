# AD-29 A function that does nothing is a claim, not a stub

An agent that writes a function
whose body is `pass`, `...` or a lone `raise NotImplementedError` has reported progress it did not
make, and every caller downstream is written against a promise. `placeholder_body` joins
`ForbiddenConstructKind` as one kind rather than three, because the three spellings state the same
thing and the spelling belongs in the record, not in the contract. Emptiness is legitimate exactly
where it is the interface: a method carrying `@abstractmethod` or `@overload`, and a method of a
class that has a base, where a protocol declares the shape and an override may deliberately do
nothing. The predicate that decides emptiness now lives in `source.py`, which both collectors
already import, instead of being written twice — collectors are peers that never import each other
([AD-25](ad-25-peers-are-isolated-by-one-rule-not-by-nn1-prohibitions.md)), and a third module for six lines would be machinery for its own sake. Check: Archkeel
declares the rule for itself and stays green, because its only two empty bodies are `Protocol`
methods; a probe with a bare `pass` fails.


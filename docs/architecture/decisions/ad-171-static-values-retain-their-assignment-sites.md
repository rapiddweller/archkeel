# AD-171 Static values retain their assignment sites

Record call-result assignments as binding entities with initializer syntax,
lexical parents and source evidence. Rebinding retains separate sites; chained
assignment shares one construction site. Older call records remain readable.

Only proven classes with inert creation and default allocation/initialization
establish nominal result types. Factories, annotations, qualified constructors,
custom creation and shadowing retain candidates. Core compares independent initializer
and instance intent. Runtime identity, lifetime and current value remain unobserved;
coverage stays partial.

[Assignment proof](../../../tests/test_static_instances.py).

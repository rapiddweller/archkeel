# Shared Python classifier kind

The five existing SymbolClassKind values belong to ir.facts because Python source collection produces them. ir.model explicitly reexports the identical enum for existing contract imports. No values, public wire fields or schema versions change.

The class-kind fixpoint carries SymbolClassKind values in its candidate set and resolved-by-definition table. Lexical winner order stays unchanged. Protocol subclasses remain ordinary classes unless Protocol is an explicit base; conditional definitions stay unclassified. Source dictionaries write the same spellings through existing StrEnum JSON behavior.

Raw and frozen records reach actual consumers through the one facts-owned parse_symbol_class_kind reader, following the existing method-kind reader. Unsupported, absent or foreign tags remain unclassified. Dart mixins stay a separate language domain. Enum/protocol decisions use nominal members without a collector-to-policy dependency.

Authored intent pins the existing enum owner and reader input/return. Focused producer checks cover forward inheritance, lexical competition, protocol inheritance, enum members, dataclass and Pydantic classification; existing classifier, boundary, state and report checks protect their behavior. Root performs combined baseline/amendment validation without changing ceilings.

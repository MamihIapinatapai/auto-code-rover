from app.spec_parser.schema import SharedWorkingMemory, StructuredSpecification

__all__ = ["StructuredSpecification", "SharedWorkingMemory"]


def __getattr__(name: str):
    if name == "SpecParsingAgent":
        from app.spec_parser.agent import SpecParsingAgent

        return SpecParsingAgent
    raise AttributeError(name)

from typing import Protocol


class Model(Protocol):
    """Provider contract; implementations must not execute tools themselves."""
    def respond(self, context: dict) -> dict: ...

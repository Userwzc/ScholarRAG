import operator
from collections.abc import Sequence
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage  # pyright: ignore[reportMissingImports]


class AgentState(TypedDict):
    messages: Annotated[Sequence[AnyMessage], operator.add]
    question: str
    attached_visuals: set[str]
    iteration_count: int

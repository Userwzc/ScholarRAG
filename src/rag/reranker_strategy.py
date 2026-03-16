"""Reranker strategy abstractions.

Defines a ``RerankerStrategy`` Protocol and a ``NoOpReranker`` null-object
implementation so that ``PaperVectorStore`` never has to branch on ``None``.
"""

from typing import Any

from typing_extensions import Protocol, runtime_checkable


@runtime_checkable
class RerankerStrategy(Protocol):
    """Interface that every reranker implementation must satisfy."""

    def process(self, inputs: dict[str, Any]) -> list[float]:
        """Score *inputs["documents"]* against *inputs["query"]*.

        Parameters
        ----------
        inputs:
            A dict with at least two keys:

            * ``"query"`` – ``{"text": str}``
            * ``"documents"`` – list of ``{"text": str}``

        Returns
        -------
        list[float]
            One relevance score per document, in the same order.
        """
        ...


class NoOpReranker:
    """Null-object reranker that returns uniform scores without doing any work.

    Used as the default ``PaperVectorStore._reranker`` when no model is
    configured, eliminating scattered ``if self._reranker is None`` guards.
    """

    def process(self, inputs: dict[str, Any]) -> list[float]:
        """Return a score of 0.0 for every document."""
        documents = inputs.get("documents", [])
        return [0.0] * len(documents)

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


SEARCH_LATENCY = Histogram(
    "rag_search_latency_seconds",
    "Search latency",
    ["tool"],
)
SEARCH_COUNTER = Counter(
    "rag_searches_total",
    "Total searches",
    ["tool"],
)
INGESTION_DURATION = Histogram(
    "ingestion_duration_seconds",
    "PDF ingestion duration",
)


@contextmanager
def record_search(tool_name: str) -> Generator[None, None, None]:
    SEARCH_COUNTER.labels(tool=tool_name).inc()
    with SEARCH_LATENCY.labels(tool=tool_name).time():
        yield


def attach_metrics_endpoint(app: FastAPI) -> None:
    if any(route.path == "/metrics" for route in app.routes):
        return

    @app.get("/metrics")
    async def _metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

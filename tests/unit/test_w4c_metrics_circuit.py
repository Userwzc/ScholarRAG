from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.utils.exceptions import ExternalServiceError
from src.utils.metrics import attach_metrics_endpoint
from src.utils.resilience import call_with_circuit_breaker


def test_metrics_endpoint_exposes_prometheus_payload() -> None:
    app = FastAPI()
    attach_metrics_endpoint(app)
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "rag_search_latency_seconds" in response.text


def test_circuit_breaker_retries_three_times_then_raises() -> None:
    state = {"count": 0}

    def _always_fail() -> str:
        state["count"] += 1
        raise ExternalServiceError("temporary failure")

    with pytest.raises(ExternalServiceError):
        call_with_circuit_breaker(_always_fail)

    assert state["count"] == 3

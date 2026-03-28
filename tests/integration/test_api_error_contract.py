# pyright: reportMissingImports=false

from io import BytesIO
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.main import app


def _assert_error_payload(payload: dict, code: str, message: str) -> None:
    assert payload == {
        "error": {
            "code": code,
            "message": message,
        }
    }


def test_client_error_returns_4xx_and_standard_payload() -> None:
    client = TestClient(app)
    response = client.post("/api/query", json={"question": "   "})

    assert response.status_code == 400
    _assert_error_payload(
        response.json(),
        code="validation_error",
        message="Question cannot be empty",
    )


def test_server_error_is_sanitized_and_standard_payload() -> None:
    client = TestClient(app)

    with patch("api.routes.query.query_service.stream_query") as mock_stream:
        mock_stream.side_effect = RuntimeError(
            "Traceback (most recent call last): secret-token-123"
        )

        response = client.post("/api/query", json={"question": "what is dream?"})

    assert response.status_code == 500
    payload = response.json()
    _assert_error_payload(
        payload,
        code="external_service_error",
        message="Query processing failed",
    )

    raw = str(payload)
    assert "Traceback" not in raw
    assert "secret-token-123" not in raw


def test_upload_server_error_is_sanitized_and_standard_payload() -> None:
    client = TestClient(app)

    with patch("api.routes.papers.get_db_session") as mock_db:
        mock_db.return_value.__aenter__ = AsyncMock(return_value=object())
        mock_db.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("api.routes.papers.async_upload_service.create_async_upload_job") as mock_create:
            mock_create.side_effect = RuntimeError("database traceback secret-password")

            files = {
                "file": (
                    "test-paper.pdf",
                    BytesIO(b"%PDF-1.4\n%mock"),
                    "application/pdf",
                )
            }
            response = client.post("/api/papers/uploads", files=files)

    assert response.status_code == 500
    payload = response.json()
    _assert_error_payload(
        payload,
        code="external_service_error",
        message="Failed to start upload processing",
    )
    raw = str(payload)
    assert "traceback" not in raw.lower()
    assert "secret-password" not in raw

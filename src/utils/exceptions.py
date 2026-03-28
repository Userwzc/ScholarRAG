from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AppError(Exception):
    message: str
    code: str = "app_error"
    status_code: int = 500
    log_message: Optional[str] = None

    def __str__(self) -> str:
        return self.log_message or self.message


class ValidationError(AppError):
    def __init__(self, message: str, log_message: Optional[str] = None) -> None:
        super().__init__(
            message=message,
            code="validation_error",
            status_code=400,
            log_message=log_message,
        )


class NotFoundError(AppError):
    def __init__(self, message: str, log_message: Optional[str] = None) -> None:
        super().__init__(
            message=message,
            code="not_found",
            status_code=404,
            log_message=log_message,
        )


class ExternalServiceError(AppError):
    def __init__(self, message: str, log_message: Optional[str] = None) -> None:
        super().__init__(
            message=message,
            code="external_service_error",
            status_code=500,
            log_message=log_message,
        )


def app_error_to_dict(error: AppError) -> dict[str, str]:
    return {
        "code": error.code,
        "message": error.message,
    }


def normalize_http_error(
    status_code: int,
    detail: object,
) -> dict[str, dict[str, str]]:
    if isinstance(detail, dict) and "error" in detail:
        error = detail.get("error")
        if isinstance(error, dict):
            code = str(error.get("code", "app_error"))
            message = str(error.get("message", "Request failed"))
            return {"error": {"code": code, "message": message}}

    if isinstance(detail, dict):
        code = str(detail.get("code", "app_error"))
        message = str(detail.get("message", "Request failed"))
        return {"error": {"code": code, "message": message}}

    message = str(detail) if detail else "Request failed"

    if status_code == 404:
        code = "not_found"
    elif 400 <= status_code < 500:
        code = "validation_error"
    else:
        code = "app_error"

    return {"error": {"code": code, "message": message}}

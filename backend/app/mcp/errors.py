"""MCP error envelope: typed error codes derived from service exceptions."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    NOT_FOUND = "not_found"
    VALIDATION_ERROR = "validation_error"
    CONFLICT = "conflict"
    GOVERNANCE_REJECTION = "governance_rejection"
    DEPENDENCY_ERROR = "dependency_error"
    INTERNAL_ERROR = "internal_error"


_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.VALIDATION_ERROR,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.VALIDATION_ERROR,
    415: ErrorCode.VALIDATION_ERROR,
    422: ErrorCode.VALIDATION_ERROR,
    428: ErrorCode.GOVERNANCE_REJECTION,
    503: ErrorCode.DEPENDENCY_ERROR,
}


def map_exception(exc: Exception) -> tuple[str, str]:
    """Return (error_code, human_message) for the given exception.

    HTTP status codes are translated to stable error codes so MCP clients do
    not need to know FastAPI semantics. ``ValueError``/``TypeError`` raised by
    service-layer input checks are treated as validation errors; anything else
    falls through to ``internal_error``.
    """
    from fastapi import HTTPException

    service_code = getattr(exc, "code", None)
    if isinstance(service_code, str):
        return service_code, str(exc)

    if isinstance(exc, HTTPException):
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return code.value, detail
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        code = _STATUS_TO_CODE.get(status_code, ErrorCode.INTERNAL_ERROR)
        return code.value, str(exc)
    if isinstance(exc, (ValueError, TypeError)):
        return ErrorCode.VALIDATION_ERROR.value, str(exc)
    return ErrorCode.INTERNAL_ERROR.value, str(exc)

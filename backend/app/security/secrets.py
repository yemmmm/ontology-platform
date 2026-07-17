from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

_PLATFORM_KEY = re.compile(r"\bsk_(?:read|model|admin)_[A-Za-z0-9]{32}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_AWS = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_BEARER = re.compile(r"(?i)\bBearer\s+([A-Za-z0-9._~+/=-]{20,})")
_CREDENTIAL_FIELDS = {
    "api_key",
    "apikey",
    "api-key",
    "password",
    "secret",
    "access_token",
    "refresh_token",
    "authorization",
}
_PLACEHOLDERS = re.compile(
    r"^(?:<[^>]+>|\$\{[^}]+\}|\*+|x+|redacted|masked|placeholder|example)$",
    re.IGNORECASE,
)


class SecretDetected(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _scan_string(value: str) -> None:
    for category, pattern in (
        ("platform_api_key", _PLATFORM_KEY),
        ("jwt", _JWT),
        ("aws_access_key", _AWS),
    ):
        if pattern.search(value):
            raise SecretDetected(category)
    match = _BEARER.search(value)
    if match and not _PLACEHOLDERS.fullmatch(match.group(1)):
        raise SecretDetected("bearer_token")


def scan_domain_payload(value: Any, *, field_name: str | None = None) -> None:
    if isinstance(value, str):
        _scan_string(value)
        if (
            field_name
            and field_name.lower().replace("-", "_")
            in {item.replace("-", "_") for item in _CREDENTIAL_FIELDS}
            and value.strip()
            and not _PLACEHOLDERS.fullmatch(value.strip())
        ):
            raise SecretDetected("credential_field")
    elif isinstance(value, dict):
        for key, child in value.items():
            scan_domain_payload(child, field_name=str(key))
    elif isinstance(value, (list, tuple)):
        for child in value:
            scan_domain_payload(child, field_name=field_name)


def reject_domain_secrets(value: Any) -> None:
    try:
        scan_domain_payload(value)
    except SecretDetected as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "secret_in_payload", "category": exc.category},
        ) from exc

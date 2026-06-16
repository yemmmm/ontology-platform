from typing import Any

from pydantic import BaseModel, Field


class ValidationIssue(BaseModel):
    path: str
    message: str
    severity: str = "error"


class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


def ok() -> ValidationResult:
    return ValidationResult(valid=True)


def error(path: str, message: str) -> ValidationResult:
    return ValidationResult(valid=False, issues=[ValidationIssue(path=path, message=message)])


def validate_properties(properties: dict[str, Any]) -> ValidationResult:
    if not isinstance(properties, dict):
        return error("properties", "Properties must be an object.")
    return ok()


from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.repositories.models import (
    FactClaimModel,
    OntologyModel,
    OntologyVersionModel,
)


def test_fact_claim_model_defaults_are_pending_and_stale_false() -> None:
    columns = {c.name: c for c in FactClaimModel.__table__.columns}
    assert columns["audit_status"].default.arg == "pending"
    assert columns["stale"].default.arg is False
    assert columns["confidence"].default.arg == 1.0

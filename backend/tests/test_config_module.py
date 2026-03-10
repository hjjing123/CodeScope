from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_default_jwt_secret_is_long_enough() -> None:
    settings = Settings()

    assert len(settings.jwt_secret.encode("utf-8")) >= 32


def test_settings_rejects_short_hs256_jwt_secret() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(jwt_secret="short-secret", jwt_algorithm="HS256")

    assert "jwt_secret is too short" in str(exc_info.value)

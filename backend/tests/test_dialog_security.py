from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.modules.dialog import api


@pytest.mark.asyncio
async def test_invalid_dialog_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api, "get_settings", lambda: Settings(dialog_api_key="expected", _env_file=None)
    )
    request = SimpleNamespace(headers={"X-API-Key": "wrong"})
    with pytest.raises(AppError) as caught:
        await api.require_dialog_key(request)
    assert caught.value.status_code == 401


@pytest.mark.asyncio
async def test_production_requires_dialog_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "get_settings", lambda: Settings(app_env="production", _env_file=None))
    request = SimpleNamespace(headers={})
    with pytest.raises(AppError) as caught:
        await api.require_dialog_key(request)
    assert caught.value.code == "AUTH_NOT_CONFIGURED"

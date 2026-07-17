import os

import pytest

from hyperbot.core.config import Settings
from hyperbot.core.retry import RetryPolicy


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYPERBOT_APP_NAME", raising=False)
    monkeypatch.delenv("HYPERBOT_EXCHANGE_NAME", raising=False)
    monkeypatch.delenv("HYPERBOT_ENABLE_WEBSOCKET", raising=False)

    settings = Settings()

    assert settings.app_name == "hyperbot"
    assert settings.exchange_name == "hyperliquid"
    assert settings.enable_websocket is True


def test_retry_policy_handles_attempts() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay=0.1, max_delay=0.5)

    assert policy.should_retry(1)
    assert policy.should_retry(2)
    assert not policy.should_retry(3)
    assert policy.next_delay(2) == 0.2

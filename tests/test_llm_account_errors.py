"""An empty provider account stops the run instead of burning per-item retries."""

from types import SimpleNamespace

import pytest

from analysis.llm.backends import ZaiBackend
from exceptions import LLMAccountError, LLMError

ZAI_EMPTY = '{"error":{"code":"1113","message":"Insufficient balance or no resource package. Please recharge."}}'


def backend_returning(*responses):
    backend = ZaiBackend("key", "glm-5.3-flash", max_retries=4, max_retry_seconds=180)
    calls = []

    def post(_body):
        calls.append(_body)
        return responses[min(len(calls), len(responses)) - 1]

    backend._post = post
    return backend, calls


def complete(backend):
    return backend.complete(
        user="u", system=None, schema=None, effort="low", max_tokens=10, temperature=0.0
    )


def test_zai_empty_balance_raises_account_error_without_retrying():
    backend, calls = backend_returning(SimpleNamespace(status_code=429, text=ZAI_EMPTY))

    with pytest.raises(LLMAccountError):
        complete(backend)

    assert len(calls) == 1


def test_plain_rate_limit_is_still_transient(monkeypatch):
    monkeypatch.setattr("analysis.llm.backends.time.sleep", lambda _s: None)
    limited = SimpleNamespace(status_code=429, text='{"error":{"code":"1302","message":"rate limit"}}')
    backend, calls = backend_returning(limited)

    with pytest.raises(LLMError) as excinfo:
        complete(backend)

    assert not isinstance(excinfo.value, LLMAccountError)
    assert len(calls) == 4

"""Global test isolation.

A developer may have a real LLM key configured in .env. Tests must never spend
money or make network calls: every test starts with the judge disabled. Individual
LLM-judge tests re-enable it explicitly with their own fake transport.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_real_llm_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_JUDGE_ENABLED", "false")

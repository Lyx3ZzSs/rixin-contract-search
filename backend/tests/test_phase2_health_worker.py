import sys

import pytest
from pydantic import ValidationError
from rq import SimpleWorker, Worker

from app.config import Settings


def test_runtime_status_redacts_llm_key_and_reports_worker_mode(client, monkeypatch):
    from app import config
    from app.api import health

    runtime_settings = Settings(
        AGENT_LLM_API_KEY="secret-runtime-key",
        AGENT_LLM_MODEL="gpt-4.1-mini",
        RQ_WORKER_MODE="simple",
    )
    monkeypatch.setattr(config, "settings", runtime_settings)
    monkeypatch.setattr(health, "settings", runtime_settings)

    response = client.get("/api/runtime/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["worker"]["mode"] == "simple"
    assert payload["llm"]["has_api_key"] is True
    assert payload["llm"]["api_key_length"] == len("secret-runtime-key")
    assert "api_key" not in payload["llm"]
    assert "secret-runtime-key" not in response.text


def test_qmd_status_reports_configured_collections(client, monkeypatch):
    from app import config
    from app.api import health

    runtime_settings = Settings(AGENT_LLM_API_KEY="test-key", QMD_COLLECTIONS="company_docs,legal_docs")

    class FakeQmdClient:
        def status(self):
            return {
                "collections": [
                    {"name": "company_docs", "count": 12},
                    {"name": "legal_docs", "document_count": 5},
                    {"name": "other_docs", "count": 2},
                ]
            }

    monkeypatch.setattr(config, "settings", runtime_settings)
    monkeypatch.setattr(health, "settings", runtime_settings)
    monkeypatch.setattr(health, "QmdClient", FakeQmdClient)

    response = client.get("/api/qmd/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["configured_collections"] == [
        {"name": "company_docs", "exists": True, "document_count": 12},
        {"name": "legal_docs", "exists": True, "document_count": 5},
    ]


def test_worker_mode_defaults_to_simple_worker_on_macos_auto(monkeypatch):
    from app.worker import choose_worker_class

    monkeypatch.setattr(sys, "platform", "darwin")

    assert choose_worker_class("auto") is SimpleWorker


def test_worker_mode_can_choose_fork():
    from app.worker import choose_worker_class

    assert choose_worker_class("fork") is Worker


def test_invalid_worker_mode_validation():
    with pytest.raises(ValidationError):
        Settings(AGENT_LLM_API_KEY="test-key", RQ_WORKER_MODE="threaded")

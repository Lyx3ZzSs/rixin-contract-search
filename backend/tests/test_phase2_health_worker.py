import sys

import pytest
from pydantic import ValidationError
from rq import SimpleWorker, Worker

from app.config import Settings


def test_url_redaction_masks_userinfo_token_passwords_and_sensitive_query_params():
    from app.config import redact_url

    assert (
        redact_url("https://qmd-token@qmd.example/mcp?access_token=secret&workspace=contracts")
        == "https://***@qmd.example/mcp"
    )
    assert redact_url("https://api.example/v1#access_token=fragment-secret") == "https://api.example/v1"
    assert redact_url("redis://worker:redis-password@redis:6379/0") == "redis://***@redis:6379/0"


def test_sanitizer_handles_freeform_secrets_and_malformed_urls():
    from app.config import sanitize_secrets

    payload = sanitize_secrets(
        "api_key=freeform-key Authorization: Bearer bearer-token "
        "Authorization: Basic basic-secret "
        "password=plain-password secret: plain-secret token plain-token "
        "client_secret=client-secret refresh_token=refresh-secret auth_token=auth-secret "
        "callback https://qmd.example:bad/mcp?api_key=query-secret#fragment-secret"
    )

    assert "freeform-key" not in payload
    assert "bearer-token" not in payload
    assert "basic-secret" not in payload
    assert "plain-password" not in payload
    assert "plain-secret" not in payload
    assert "plain-token" not in payload
    assert "client-secret" not in payload
    assert "refresh-secret" not in payload
    assert "auth-secret" not in payload
    assert "query-secret" not in payload
    assert "fragment-secret" not in payload
    assert "https://qmd.example/mcp" in payload


def test_sanitizer_redacts_credentialed_non_http_dsns():
    from app.config import sanitize_secrets

    payload = sanitize_secrets(
        "redis redis://worker:redis-password@redis:6379/0 "
        "postgres postgresql://user:db-password@db/contracts "
        "mysql mysql://user:mysql-password@mysql/contracts "
        "mongo mongodb://user:mongo-password@mongo/contracts "
        "amqp amqp://user:amqp-password@mq/vhost"
    )

    for secret in ("redis-password", "db-password", "mysql-password", "mongo-password", "amqp-password"):
        assert secret not in payload
    assert "redis://***@redis:6379/0" in payload
    assert "postgresql://***@db/contracts" in payload
    assert "mysql://***@mysql/contracts" in payload
    assert "mongodb://***@mongo/contracts" in payload
    assert "amqp://***@mq/vhost" in payload


def test_runtime_status_redacts_llm_key_and_reports_worker_mode(client, monkeypatch):
    from app import config
    from app.api import health

    redis_secret = "redis-password"
    qmd_secret = "qmd-token"
    runtime_settings = Settings(
        AGENT_LLM_API_KEY="secret-runtime-key",
        AGENT_LLM_BASE_URL="https://llm-user:llm-password@llm.example/v1?api_key=llm-query-key#access_token=llm-fragment",
        AGENT_LLM_MODEL="gpt-4.1-mini",
        REDIS_URL=f"redis://worker:{redis_secret}@redis:6379/0",
        QMD_MCP_URL=f"https://qmd.example/mcp?token={qmd_secret}&workspace=contracts",
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
    assert redis_secret not in response.text
    assert qmd_secret not in response.text
    assert "llm-password" not in response.text
    assert "llm-query-key" not in response.text
    assert "llm-fragment" not in response.text
    assert payload["llm"]["base_url"] == "https://***@llm.example/v1"
    assert payload["redis"]["url"] == "redis://***@redis:6379/0"
    assert payload["qmd"]["url"] == "https://qmd.example/mcp"


def test_qmd_status_reports_configured_collections_and_redacts_url(client, monkeypatch):
    from app import config
    from app.api import health

    qmd_secret = "qmd-token"
    runtime_settings = Settings(
        AGENT_LLM_API_KEY="test-key",
        QMD_COLLECTIONS="company_docs,legal_docs",
        QMD_MCP_URL=f"https://user:qmd-password@qmd.example/mcp?token={qmd_secret}&debug=true",
    )

    class FakeQmdClient:
        def status(self):
            return {
                "collections": [
                    {"name": "company_docs", "count": 12},
                    {"name": "legal_docs", "files": 5},
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
    assert qmd_secret not in response.text
    assert "qmd-password" not in response.text
    assert payload["url"] == "https://***@qmd.example/mcp"
    assert payload["configured_collections"] == [
        {"name": "company_docs", "exists": True, "document_count": 12},
        {"name": "legal_docs", "exists": True, "document_count": 5},
    ]


def test_qmd_status_redacts_url_secrets_from_unavailable_error(client, monkeypatch):
    from app import config
    from app.api import health
    from app.services.retrieval.qmd_client import QmdUnavailable

    configured_qmd_url = "https://user:qmd-password@qmd.example/mcp/?token=qmd-token"
    normalized_qmd_url = "https://user:qmd-password@qmd.example/mcp?token=qmd-token"
    runtime_settings = Settings(AGENT_LLM_API_KEY="test-key", QMD_MCP_URL=configured_qmd_url)

    class FakeQmdClient:
        def status(self):
            raise QmdUnavailable(f"qmd MCP returned empty response from {normalized_qmd_url}")

    monkeypatch.setattr(config, "settings", runtime_settings)
    monkeypatch.setattr(health, "settings", runtime_settings)
    monkeypatch.setattr(health, "QmdClient", FakeQmdClient)

    response = client.get("/api/qmd/status")

    assert response.status_code == 200
    assert "qmd-password" not in response.text
    assert "qmd-token" not in response.text
    assert response.json()["error"]["message"] == (
        "qmd MCP returned empty response from https://***@qmd.example/mcp"
    )


def test_qmd_status_sanitizes_structured_exception_args(client, monkeypatch):
    from app import config
    from app.api import health
    from app.services.retrieval.qmd_client import QmdUnavailable

    runtime_settings = Settings(AGENT_LLM_API_KEY="test-key")

    class FakeQmdClient:
        def status(self):
            raise QmdUnavailable({"api_key": "payload-api-key", "detail": ["Authorization: Bearer payload-bearer"]})

    monkeypatch.setattr(config, "settings", runtime_settings)
    monkeypatch.setattr(health, "settings", runtime_settings)
    monkeypatch.setattr(health, "QmdClient", FakeQmdClient)

    response = client.get("/api/qmd/status")

    assert response.status_code == 200
    assert "payload-api-key" not in response.text
    assert "payload-bearer" not in response.text
    assert response.json()["error"]["message"] == "{'api_key': '***', 'detail': ['Authorization: Bearer ***']}"


def test_qmd_status_recursively_sanitizes_upstream_payload(client, monkeypatch):
    from app import config
    from app.api import health

    runtime_settings = Settings(AGENT_LLM_API_KEY="test-key")

    class FakeQmdClient:
        def status(self):
            return {
                "collections": [{"name": "company_docs", "files": 3}],
                "metadata": {
                    "source_url": "https://user:payload-password@qmd.example/source?token=payload-token#access_token=fragment-token",
                    "api_key": "payload-api-key",
                    "authorization": "Bearer payload-bearer",
                    "nested": [{"secret": "payload-secret"}, "https://qmd.example/raw?debug=payload-debug"],
                },
            }

    monkeypatch.setattr(config, "settings", runtime_settings)
    monkeypatch.setattr(health, "settings", runtime_settings)
    monkeypatch.setattr(health, "QmdClient", FakeQmdClient)

    response = client.get("/api/qmd/status")

    assert response.status_code == 200
    assert "payload-password" not in response.text
    assert "payload-token" not in response.text
    assert "fragment-token" not in response.text
    assert "payload-api-key" not in response.text
    assert "payload-bearer" not in response.text
    assert "payload-secret" not in response.text
    assert "payload-debug" not in response.text
    metadata = response.json()["status"]["metadata"]
    assert metadata["source_url"] == "https://***@qmd.example/source"
    assert metadata["api_key"] == "***"
    assert metadata["authorization"] == "***"
    assert metadata["nested"] == [{"secret": "***"}, "https://qmd.example/raw"]


def test_worker_mode_defaults_to_simple_worker_on_macos_auto(monkeypatch):
    from app.worker import choose_worker_class

    monkeypatch.setattr(sys, "platform", "darwin")

    assert choose_worker_class("auto") is SimpleWorker


def test_worker_mode_can_choose_fork():
    from app.worker import choose_worker_class

    assert choose_worker_class("fork") is Worker


def test_worker_startup_diagnostics_redact_url_secrets(monkeypatch, capsys):
    from app import worker

    redis_secret = "redis-password"
    qmd_secret = "qmd-token"
    runtime_settings = Settings(
        AGENT_LLM_API_KEY="test-key",
        AGENT_LLM_BASE_URL="https://llm-user:llm-password@llm.example/v1?api_key=llm-query-key#access_token=llm-fragment",
        REDIS_URL=f"redis://worker:{redis_secret}@redis:6379/0",
        QMD_MCP_URL=f"https://user:qmd-password@qmd.example/mcp?access_token={qmd_secret}",
        RQ_WORKER_MODE="simple",
    )

    class FakeRedis:
        @classmethod
        def from_url(cls, url):
            return cls()

    class FakeWorker:
        def __init__(self, queues, connection):
            self.queues = queues
            self.connection = connection

        def work(self):
            return False

    monkeypatch.setattr(worker, "settings", runtime_settings)
    monkeypatch.setattr(worker, "Redis", FakeRedis)
    monkeypatch.setattr(worker, "choose_worker_class", lambda mode: FakeWorker)

    worker.main()

    output = capsys.readouterr().out
    assert redis_secret not in output
    assert qmd_secret not in output
    assert "qmd-password" not in output
    assert "llm-password" not in output
    assert "llm-query-key" not in output
    assert "llm-fragment" not in output


def test_invalid_worker_mode_validation():
    with pytest.raises(ValidationError):
        Settings(AGENT_LLM_API_KEY="test-key", RQ_WORKER_MODE="threaded")

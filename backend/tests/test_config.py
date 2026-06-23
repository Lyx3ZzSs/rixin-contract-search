from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import PROJECT_ENV_FILE, Settings


def test_settings_env_file_is_project_root_absolute_path():
    expected = Path(__file__).resolve().parents[2] / ".env"

    assert PROJECT_ENV_FILE == expected
    assert Path(Settings.model_config["env_file"]).is_absolute()
    assert Settings.model_config["env_file"] == expected


def test_qmd_mcp_settings_validation():
    settings = Settings(QMD_BACKEND="mcp", QMD_MCP_URL="http://localhost:8181/mcp", QMD_COLLECTIONS=" company_docs, legal_docs ")

    assert settings.QMD_BACKEND == "mcp"
    assert settings.QMD_COLLECTIONS == "company_docs,legal_docs"

    with pytest.raises(ValidationError):
        Settings(QMD_BACKEND="cli")
    with pytest.raises(ValidationError):
        Settings(QMD_MCP_URL="localhost:8181/mcp")
    with pytest.raises(ValidationError):
        Settings(QMD_COLLECTIONS=" , ")


def test_internal_owner_settings_validation():
    assert Settings(INTERNAL_OWNER_ID="internal-user").INTERNAL_OWNER_ID == "internal-user"
    with pytest.raises(ValidationError):
        Settings(INTERNAL_OWNER_ID="")


def test_static_token_auth_settings_are_removed():
    settings = Settings()

    assert not hasattr(settings, "AUTH_MODE")
    assert not hasattr(settings, "APP_AUTH_TOKENS")
    assert not hasattr(settings, "auth_token_map")


def test_parsing_service_settings_validation():
    assert Settings(PARSING_SERVICE_URL=" https://parser.example/parse ", PARSING_SERVICE_PROVIDER=" enterprise ").PARSING_SERVICE_PROVIDER == "enterprise"
    assert Settings(PARSING_SERVICE_URL="https://parser.example/parse", PARSING_SERVICE_PROVIDER="custom").PARSING_SERVICE_PROVIDER == "custom"
    for url in ["", "ftp://parser.example/parse", "parser.example/parse"]:
        with pytest.raises(ValidationError):
            Settings(PARSING_SERVICE_URL=url)
    for provider in ["fake", "legacy"]:
        with pytest.raises(ValidationError):
            Settings(PARSING_SERVICE_URL="https://parser.example/parse", PARSING_SERVICE_PROVIDER=provider)


def test_agent_settings_validation():
    settings = Settings(
        AGENT_BACKEND=" langgraph ",
        AGENT_LLM_BASE_URL=" https://llm.example/v1 ",
        AGENT_LLM_API_KEY=" secret ",
        AGENT_LLM_MODEL=" gpt-4.1-mini ",
        AGENT_LLM_TEMPERATURE=0,
        AGENT_MAX_RETRIEVAL_ROUNDS=2,
    )

    assert settings.AGENT_BACKEND == "langgraph"
    assert settings.AGENT_LLM_BASE_URL == "https://llm.example/v1"
    assert settings.AGENT_LLM_API_KEY == "secret"
    assert settings.AGENT_LLM_MODEL == "gpt-4.1-mini"
    assert settings.AGENT_MAX_RETRIEVAL_ROUNDS == 2

    with pytest.raises(ValidationError):
        Settings(AGENT_BACKEND="crew")
    with pytest.raises(ValidationError):
        Settings(AGENT_LLM_BASE_URL="llm.example/v1")
    with pytest.raises(ValidationError):
        Settings(AGENT_MAX_RETRIEVAL_ROUNDS=0)
    with pytest.raises(ValidationError):
        Settings(AGENT_LLM_API_KEY="")
    with pytest.raises(ValidationError):
        Settings(AGENT_LLM_API_KEY="secret", AGENT_LLM_MODEL="fake")

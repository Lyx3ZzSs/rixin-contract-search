from functools import lru_cache
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ENV_FILE = PROJECT_ROOT / ".env"
SENSITIVE_KEY_MARKERS = ("token", "key", "secret", "password", "pwd", "auth", "credential")
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|password|passwd|pwd|secret|credential)\b"
    r"(\s*[:=]\s*)"
    r"([^\s,;]+)"
)
SECRET_WORD_PATTERN = re.compile(r"(?i)\b(token|password|secret|credential)\b(\s+)([^\s,;]+)")
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+([^\s,;]+)")
AUTH_HEADER_PATTERN = re.compile(r"(?i)\bAuthorization\s*:\s*(?!Bearer\b)([^\s,;]+)")


def redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "***"
    netloc = parsed.netloc
    if parsed.username is not None:
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        try:
            port_value = parsed.port
        except ValueError:
            port_value = None
        port = f":{port_value}" if port_value is not None else ""
        netloc = f"***@{host}{port}"
    elif parsed.netloc:
        host = parsed.hostname or parsed.netloc.split(":", 1)[0]
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        try:
            port_value = parsed.port
        except ValueError:
            port_value = None
        port = f":{port_value}" if port_value is not None else ""
        netloc = f"{host}{port}"

    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def sanitize_secrets(value):
    if isinstance(value, dict):
        return {
            key: "***" if is_sensitive_key(key) else sanitize_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_secrets(item) for item in value)
    if isinstance(value, str):
        return sanitize_secret_string(value)
    return value


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower()
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)


def sanitize_secret_string(value: str) -> str:
    sanitized = URL_PATTERN.sub(redact_url_match, value)
    sanitized = BEARER_PATTERN.sub("Bearer ***", sanitized)
    sanitized = AUTH_HEADER_PATTERN.sub("Authorization: ***", sanitized)
    sanitized = SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2***", sanitized)
    return SECRET_WORD_PATTERN.sub(r"\1\2***", sanitized)


def redact_url_match(match: re.Match[str]) -> str:
    url = match.group(0)
    trailing = ""
    while url and url[-1] in ".,;:)]}":
        trailing = url[-1] + trailing
        url = url[:-1]
    return f"{redact_url(url)}{trailing}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ENV_FILE, extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://contract:contract@postgres:5432/contracts"
    TEST_DATABASE_URL: str = "sqlite+pysqlite:///:memory:"
    REDIS_URL: str = "redis://redis:6379/0"
    STORAGE_ROOT: str = "/data/storage"
    INTERNAL_OWNER_ID: str = "internal-user"
    PARSING_SERVICE_URL: str = "https://parser.example.internal/parse"
    PARSING_SERVICE_API_KEY: str = ""
    PARSING_SERVICE_PROVIDER: str = "enterprise"
    QMD_BACKEND: str = "mcp"
    QMD_MCP_URL: str = "http://localhost:8181/mcp"
    QMD_COLLECTIONS: str = "company_docs"
    QMD_TOP_K: int = 50
    AGENT_BACKEND: str = "langgraph"
    AGENT_LLM_BASE_URL: str = "https://api.openai.com/v1"
    AGENT_LLM_API_KEY: str = ""
    AGENT_LLM_MODEL: str = "gpt-4.1-mini"
    AGENT_LLM_TEMPERATURE: float = 0
    AGENT_MAX_RETRIEVAL_ROUNDS: int = 2
    RQ_WORKER_MODE: str = "auto"
    MAX_UPLOAD_MB: int = 50
    MAX_FILES_PER_TASK: int = 5
    MAX_PAGES_PER_FILE: int = 200
    SSE_KEEPALIVE_SECONDS: int = 15

    @field_validator("STORAGE_ROOT")
    @classmethod
    def validate_storage_root(cls, value: str) -> str:
        if not Path(value).is_absolute():
            raise ValueError("STORAGE_ROOT must be an absolute path")
        return value

    @field_validator("QMD_BACKEND")
    @classmethod
    def validate_qmd_backend(cls, value: str) -> str:
        value = value.strip()
        if value not in {"mcp", "fixture"}:
            raise ValueError("QMD_BACKEND must be mcp or fixture")
        return value

    @field_validator("QMD_MCP_URL")
    @classmethod
    def validate_qmd_mcp_url(cls, value: str) -> str:
        value = value.strip()
        if not value or not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("QMD_MCP_URL must be an http or https URL")
        return value

    @field_validator("QMD_COLLECTIONS")
    @classmethod
    def validate_qmd_collections(cls, value: str) -> str:
        collections = [item.strip() for item in value.split(",") if item.strip()]
        if not collections:
            raise ValueError("QMD_COLLECTIONS must include at least one collection")
        return ",".join(collections)

    @field_validator("AGENT_BACKEND")
    @classmethod
    def validate_agent_backend(cls, value: str) -> str:
        value = value.strip()
        if value not in {"langgraph"}:
            raise ValueError("AGENT_BACKEND must be langgraph")
        return value

    @field_validator("AGENT_LLM_BASE_URL")
    @classmethod
    def validate_agent_llm_base_url(cls, value: str) -> str:
        value = value.strip()
        if not value or not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("AGENT_LLM_BASE_URL must be an http or https URL")
        return value.rstrip("/")

    @field_validator("AGENT_LLM_API_KEY")
    @classmethod
    def trim_agent_llm_api_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("AGENT_LLM_API_KEY is required")
        return value

    @field_validator("AGENT_LLM_MODEL")
    @classmethod
    def trim_agent_llm_model(cls, value: str) -> str:
        value = value.strip()
        if not value or value == "fake":
            raise ValueError("AGENT_LLM_MODEL must be a real OpenAI-compatible model name")
        return value

    @field_validator("RQ_WORKER_MODE")
    @classmethod
    def validate_rq_worker_mode(cls, value: str) -> str:
        value = value.strip()
        if value not in {"auto", "simple", "fork"}:
            raise ValueError("RQ_WORKER_MODE must be auto, simple, or fork")
        return value

    @field_validator("PARSING_SERVICE_URL")
    @classmethod
    def validate_parsing_service_url(cls, value: str) -> str:
        value = value.strip()
        if not value or not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("PARSING_SERVICE_URL must be an http or https URL")
        return value

    @field_validator("PARSING_SERVICE_API_KEY")
    @classmethod
    def trim_parsing_service_api_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("PARSING_SERVICE_PROVIDER")
    @classmethod
    def validate_parsing_service_provider(cls, value: str) -> str:
        value = value.strip()
        if value not in {"enterprise", "custom"}:
            raise ValueError("PARSING_SERVICE_PROVIDER must be enterprise or custom")
        return value

    @field_validator("INTERNAL_OWNER_ID")
    @classmethod
    def validate_internal_owner_id(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 128:
            raise ValueError("INTERNAL_OWNER_ID must be 1-128 characters")
        return value

    @model_validator(mode="after")
    def validate_numbers(self) -> "Settings":
        for name in ("MAX_UPLOAD_MB", "MAX_FILES_PER_TASK", "MAX_PAGES_PER_FILE", "QMD_TOP_K", "SSE_KEEPALIVE_SECONDS", "AGENT_MAX_RETRIEVAL_ROUNDS"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if not 0 <= self.AGENT_LLM_TEMPERATURE <= 2:
            raise ValueError("AGENT_LLM_TEMPERATURE must be between 0 and 2")
        if self.MAX_FILES_PER_TASK != 5:
            raise ValueError("MAX_FILES_PER_TASK must equal 5 in Phase 1")
        if not 1 <= self.SSE_KEEPALIVE_SECONDS <= 300:
            raise ValueError("SSE_KEEPALIVE_SECONDS must be between 1 and 300")
        return self

    def redacted_runtime_status(self) -> dict[str, object]:
        api_key = self.AGENT_LLM_API_KEY
        return {
            "env": {"file": str(self.model_config["env_file"])},
            "llm": {
                "base_url": redact_url(self.AGENT_LLM_BASE_URL),
                "model": self.AGENT_LLM_MODEL,
                "has_api_key": bool(api_key),
                "api_key_length": len(api_key),
            },
            "qmd": {
                "backend": self.QMD_BACKEND,
                "url": redact_url(self.QMD_MCP_URL),
                "collections": [item.strip() for item in self.QMD_COLLECTIONS.split(",") if item.strip()],
            },
            "redis": {"url": redact_url(self.REDIS_URL)},
            "worker": {"mode": self.RQ_WORKER_MODE},
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from app.config import settings


PARSE_REJECTED = "Parsing service rejected the file"
PARSE_UNAVAILABLE = "Parsing service unavailable"
PARSE_TIMEOUT = "Parsing service request timed out"
PARSE_INVALID = "Parsing service returned an invalid response"


class ParseServiceFailed(Exception):
    def __init__(self, error_code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.retryable = retryable


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class ParsePage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page_number: int
    markdown: str

    @field_validator("page_number", mode="before")
    @classmethod
    def validate_page_number(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("page_number must be a positive integer")
        return value

    @field_validator("markdown", mode="before")
    @classmethod
    def validate_markdown(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("markdown must be a string")
        return value


class ParseEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page: int
    bbox: list[float] | None = None
    text: str
    kind: Literal["text", "table", "title", "footer", "header"] = "text"
    confidence: float | None = None

    @field_validator("page", mode="before")
    @classmethod
    def validate_page(cls, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("page must be a positive integer")
        return value

    @field_validator("bbox", mode="before")
    @classmethod
    def validate_bbox(cls, value: Any) -> list[float] | None:
        if value is None:
            return value
        if not isinstance(value, list) or len(value) != 4 or any(not _is_number(item) for item in value):
            raise ValueError("bbox must contain exactly four numbers")
        return value

    @field_validator("text", mode="before")
    @classmethod
    def validate_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("text must be a string")
        value = value.strip()
        if not value:
            raise ValueError("text must not be empty")
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> float | None:
        if value is None:
            return value
        if not _is_number(value) or not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


class ParseResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parser_name: str
    parser_version: str
    provider_request_id: str | None = None
    quality: dict[str, Any]
    contract_markdown: str
    pages: list[ParsePage]
    evidence: list[ParseEvidence]
    metadata: dict[str, Any]

    @field_validator("parser_name", "parser_version", mode="before")
    @classmethod
    def validate_parser_text(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("invalid parser metadata")
        value = value.strip()
        if not value or len(value) > 128:
            raise ValueError("invalid parser metadata")
        return value

    @field_validator("provider_request_id", mode="before")
    @classmethod
    def validate_provider_request_id(cls, value: Any) -> str | None:
        if value is None:
            return value
        if not isinstance(value, str):
            raise ValueError("provider_request_id must be a string")
        value = value.strip()
        if not value:
            return None
        if len(value) > 256:
            raise ValueError("provider_request_id is too long")
        return value

    @field_validator("quality", "metadata", mode="before")
    @classmethod
    def validate_dict_fields(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("field must be a dict")
        return value

    @field_validator("contract_markdown", mode="before")
    @classmethod
    def validate_contract_markdown(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("contract_markdown must be a string")
        return value

    @field_validator("pages")
    @classmethod
    def validate_pages(cls, value: list[ParsePage]) -> list[ParsePage]:
        if not value:
            raise ValueError("pages must not be empty")
        seen = set()
        for page in value:
            if page.page_number in seen:
                raise ValueError("duplicate page_number")
            seen.add(page.page_number)
        return value

    @model_validator(mode="after")
    def validate_quality_and_metadata(self) -> "ParseResult":
        confidence = self.quality.get("ocr_confidence")
        if confidence is not None and (not _is_number(confidence) or not 0 <= confidence <= 1):
            raise ValueError("invalid ocr_confidence")
        warnings = self.quality.get("warnings")
        if "warnings" in self.quality and (not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings)):
            raise ValueError("invalid warnings")
        page_count = self.metadata.get("page_count")
        if page_count is not None and (isinstance(page_count, bool) or not isinstance(page_count, int) or page_count <= 0):
            raise ValueError("invalid page_count")
        return self


class UnifiedParsingServiceClient:
    def parse_file(self, contract_id: UUID, file_path: Path, filename: str) -> ParseResult:
        headers = {"X-API-Key": settings.PARSING_SERVICE_API_KEY} if settings.PARSING_SERVICE_API_KEY else {}
        last_error: ParseServiceFailed | None = None
        for attempt in range(2):
            try:
                with file_path.open("rb") as handle:
                    response = httpx.post(
                        settings.PARSING_SERVICE_URL,
                        headers=headers,
                        files={"file": (filename, handle)},
                        data={"contract_id": str(contract_id)},
                        timeout=120,
                    )
                if 300 <= response.status_code < 500:
                    raise ParseServiceFailed("parse_service_rejected", PARSE_REJECTED, False)
                if response.status_code >= 500:
                    raise ParseServiceFailed("parse_service_unavailable", PARSE_UNAVAILABLE, True)
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ParseServiceFailed("parse_service_invalid_response", PARSE_INVALID, False) from exc
                return normalize_response(payload)
            except httpx.TimeoutException:
                last_error = ParseServiceFailed("parse_service_timeout", PARSE_TIMEOUT, True)
            except httpx.TransportError:
                last_error = ParseServiceFailed("parse_service_unavailable", PARSE_UNAVAILABLE, True)
            except ParseServiceFailed as exc:
                last_error = exc
                if not exc.retryable:
                    raise
            if attempt == 1 and last_error is not None:
                raise last_error
        raise ParseServiceFailed("parse_service_unavailable", PARSE_UNAVAILABLE, True)


def normalize_response(payload: Any) -> ParseResult:
    if not isinstance(payload, dict):
        raise ParseServiceFailed("parse_service_invalid_response", PARSE_INVALID, False)
    try:
        sanitized = redact_secret(payload, settings.PARSING_SERVICE_API_KEY)
        prepared = normalize_evidence_pages(sanitized)
        response = ParseResult.model_validate(prepared)
        valid_pages = {page.page_number for page in response.pages}
        evidence = [item for item in response.evidence if item.page in valid_pages]
        if len(evidence) != len(response.evidence):
            response = response.model_copy(update={"evidence": evidence})
        return response
    except (ValidationError, ValueError) as exc:
        raise ParseServiceFailed("parse_service_invalid_response", PARSE_INVALID, False) from exc


def normalize_evidence_pages(payload: dict[str, Any]) -> dict[str, Any]:
    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list):
        raise ValueError("evidence must be a list")
    evidence = []
    for item in raw_evidence:
        if not isinstance(item, dict):
            raise ValueError("evidence entries must be objects")
        page = item.get("page")
        if isinstance(page, bool) or page is None or not isinstance(page, int):
            raise ValueError("invalid evidence page")
        if page <= 0:
            continue
        evidence.append(item)
    return {**payload, "evidence": evidence}


def redact_secret(value: Any, secret: str) -> Any:
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, list):
        return [redact_secret(item, secret) for item in value]
    if isinstance(value, dict):
        return {redact_secret(key, secret) if isinstance(key, str) else key: redact_secret(item, secret) for key, item in value.items()}
    return value


def is_low_quality(response: ParseResult) -> bool:
    quality = response.quality or {}
    warnings = quality.get("warnings") or []
    if quality.get("ocr_confidence") is not None and quality["ocr_confidence"] < 0.65:
        return True
    if not response.contract_markdown.strip():
        return True
    page_count = response.metadata.get("page_count")
    if page_count is not None and page_count != len(response.pages):
        return True
    return "table_parse_failed" in warnings or "empty_text" in warnings

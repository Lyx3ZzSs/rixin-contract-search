from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.services.parsing.unified_parser_client import (
    ParseServiceFailed,
    UnifiedParsingServiceClient,
    is_low_quality,
    normalize_response,
)


def valid_payload(**overrides):
    payload = {
        "parser_name": "enterprise-parser",
        "parser_version": "0.1",
        "provider_request_id": "job-123",
        "quality": {"ocr_confidence": 0.9, "warnings": []},
        "contract_markdown": "合同总价为人民币120万元",
        "pages": [{"page_number": 1, "markdown": "合同总价为人民币120万元"}],
        "evidence": [{"page": 1, "bbox": [0, 0, 100, 20], "text": "合同总价为人民币120万元", "kind": "text", "confidence": 0.9}],
        "metadata": {"page_count": 1},
    }
    payload.update(overrides)
    return payload


def test_normalize_response_sanitizes_and_normalizes(monkeypatch):
    monkeypatch.setattr("app.services.parsing.unified_parser_client.settings.PARSING_SERVICE_API_KEY", "secret-key")
    result = normalize_response(
        valid_payload(
            provider_request_id="job-secret-key",
            quality={"ocr_confidence": 0.9, "warnings": [], "token": "secret-key"},
            metadata={"page_count": 1, "secret-key_trace": "ok"},
            evidence=[
                {"page": 0, "text": "dropped", "kind": "text"},
                {"page": 999, "text": "dangling", "kind": "text"},
                {"page": 1, "bbox": [0, 0, 1, 1], "text": "secret-key evidence", "kind": "text", "confidence": 1},
            ],
            ignored_top_level="secret-key",
        )
    )

    assert result.provider_request_id == "job-[REDACTED]"
    assert result.quality["token"] == "[REDACTED]"
    assert "[REDACTED]_trace" in result.metadata
    assert len(result.evidence) == 1
    assert result.evidence[0].text == "[REDACTED] evidence"


@pytest.mark.parametrize(
    "override",
    [
        {"pages": []},
        {"pages": [{"page_number": 1, "markdown": "a"}, {"page_number": 1, "markdown": "b"}]},
        {"pages": [{"page_number": True, "markdown": "a"}]},
        {"evidence": [None]},
        {"evidence": [{"text": "missing page"}]},
        {"evidence": [{"page": "1", "text": "bad page"}]},
        {"evidence": [{"page": 1, "bbox": [0, 1, 2], "text": "bad bbox"}]},
        {"evidence": [{"page": 1, "bbox": [0, 1, 2, True], "text": "bad bbox"}]},
        {"evidence": [{"page": 1, "text": "", "kind": "text"}]},
        {"evidence": [{"page": 1, "text": "x", "kind": "unknown"}]},
        {"evidence": [{"page": 1, "text": "x", "confidence": 1.5}]},
        {"quality": {"ocr_confidence": True, "warnings": []}},
        {"quality": {"ocr_confidence": 2, "warnings": []}},
        {"quality": {"warnings": None}},
        {"quality": {"warnings": ["ok", 1]}},
        {"metadata": {"page_count": 0}},
        {"metadata": {"page_count": "1"}},
    ],
)
def test_normalize_response_rejects_invalid_payloads(override):
    with pytest.raises(ParseServiceFailed) as exc:
        normalize_response(valid_payload(**override))
    assert exc.value.error_code == "parse_service_invalid_response"
    assert exc.value.message == "Parsing service returned an invalid response"


def test_page_count_mismatch_is_low_quality_not_invalid():
    result = normalize_response(valid_payload(metadata={"page_count": 2}))
    assert is_low_quality(result) is True


def test_client_sends_trimmed_api_key_and_omits_blank_key(tmp_path, monkeypatch):
    calls = []
    path = tmp_path / "contract.png"
    path.write_bytes(b"image")

    def fake_post(url, headers=None, files=None, data=None, timeout=None):
        calls.append({"url": url, "headers": headers or {}, "data": data, "timeout": timeout})
        return httpx.Response(200, json=valid_payload())

    monkeypatch.setattr("app.services.parsing.unified_parser_client.httpx.post", fake_post)
    monkeypatch.setattr("app.services.parsing.unified_parser_client.settings.PARSING_SERVICE_URL", "https://parser.example/parse")
    monkeypatch.setattr("app.services.parsing.unified_parser_client.settings.PARSING_SERVICE_API_KEY", "trimmed-key")

    UnifiedParsingServiceClient().parse_file(uuid4(), path, "contract.png")
    assert calls[-1]["headers"]["X-API-Key"] == "trimmed-key"
    assert calls[-1]["timeout"] == 120

    monkeypatch.setattr("app.services.parsing.unified_parser_client.settings.PARSING_SERVICE_API_KEY", "")
    UnifiedParsingServiceClient().parse_file(uuid4(), path, "contract.png")
    assert "X-API-Key" not in calls[-1]["headers"]


@pytest.mark.parametrize(
    ("responses", "error_code", "message", "expected_calls"),
    [
        ([httpx.Response(302), httpx.Response(200, json=valid_payload())], "parse_service_rejected", "Parsing service rejected the file", 1),
        ([httpx.Response(400), httpx.Response(200, json=valid_payload())], "parse_service_rejected", "Parsing service rejected the file", 1),
        ([httpx.Response(500), httpx.Response(500)], "parse_service_unavailable", "Parsing service unavailable", 2),
        ([httpx.Response(200, content=b"not-json")], "parse_service_invalid_response", "Parsing service returned an invalid response", 1),
        ([httpx.Response(200, json=valid_payload(pages=[]))], "parse_service_invalid_response", "Parsing service returned an invalid response", 1),
    ],
)
def test_client_failure_mapping_and_retry_counts(tmp_path, monkeypatch, responses, error_code, message, expected_calls):
    path = tmp_path / "contract.png"
    path.write_bytes(b"image")
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return responses[len(calls) - 1]

    monkeypatch.setattr("app.services.parsing.unified_parser_client.httpx.post", fake_post)
    monkeypatch.setattr("app.services.parsing.unified_parser_client.settings.PARSING_SERVICE_API_KEY", "secret-key")

    with pytest.raises(ParseServiceFailed) as exc:
        UnifiedParsingServiceClient().parse_file(uuid4(), path, "contract.png")
    assert exc.value.error_code == error_code
    assert exc.value.message == message
    assert "secret-key" not in exc.value.message
    assert len(calls) == expected_calls


def test_client_retries_retryable_failure_then_returns_success(tmp_path, monkeypatch):
    path = tmp_path / "contract.png"
    path.write_bytes(b"image")
    responses = [httpx.Response(500), httpx.Response(200, json=valid_payload())]
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return responses[len(calls) - 1]

    monkeypatch.setattr("app.services.parsing.unified_parser_client.httpx.post", fake_post)

    result = UnifiedParsingServiceClient().parse_file(uuid4(), path, "contract.png")

    assert result.parser_name == "enterprise-parser"
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("exception", "error_code", "message"),
    [
        (httpx.TimeoutException("timeout"), "parse_service_timeout", "Parsing service request timed out"),
        (httpx.ConnectError("connect failed"), "parse_service_unavailable", "Parsing service unavailable"),
    ],
)
def test_client_transport_failures_retry_once(tmp_path, monkeypatch, exception, error_code, message):
    path = tmp_path / "contract.png"
    path.write_bytes(b"image")
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        raise exception

    monkeypatch.setattr("app.services.parsing.unified_parser_client.httpx.post", fake_post)

    with pytest.raises(ParseServiceFailed) as exc:
        UnifiedParsingServiceClient().parse_file(uuid4(), path, "contract.png")
    assert exc.value.error_code == error_code
    assert exc.value.message == message
    assert len(calls) == 2

import json

import pytest

from app.services.retrieval.qmd_client import QmdClient, QmdUnavailable


class FakeResponse:
    def __init__(self, status_code: int, body: str = "", headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.content = body.encode()
        self.text = body
        self.headers = headers or {}

    def json(self):
        return json.loads(self.text)


class FakeHttpxClient:
    responses: list[FakeResponse] = []
    calls: list[dict] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def post(self, url, json, headers):
        self.calls.append({"url": url, "json": json, "headers": headers, "kwargs": self.kwargs})
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def reset_fake_http_client(monkeypatch):
    import app.services.retrieval.qmd_client as qmd_client

    FakeHttpxClient.responses = []
    FakeHttpxClient.calls = []
    monkeypatch.setattr(qmd_client.httpx, "Client", FakeHttpxClient)


def test_initialized_notification_accepts_empty_202_response():
    FakeHttpxClient.responses = [
        FakeResponse(200, '{"result":{"protocolVersion":"2024-11-05"}}', {"mcp-session-id": "session-1"}),
        FakeResponse(202, ""),
        FakeResponse(200, '{"result":{"structuredContent":{"collections":[{"name":"contract_docs"}]}}}'),
    ]

    status = QmdClient(url="http://localhost:8181/mcp").status()

    assert status == {"collections": [{"name": "contract_docs"}]}
    assert FakeHttpxClient.calls[1]["json"]["method"] == "notifications/initialized"
    assert FakeHttpxClient.calls[0]["kwargs"]["trust_env"] is False


def test_query_normalizes_structured_results_with_page_numbers():
    FakeHttpxClient.responses = [
        FakeResponse(200, '{"result":{"protocolVersion":"2024-11-05"}}', {"mcp-session-id": "session-1"}),
        FakeResponse(202, ""),
        FakeResponse(
            200,
            json.dumps(
                {
                    "result": {
                        "structuredContent": {
                            "results": [
                                {
                                    "file": "qmd://company_docs/contracts/a.md",
                                    "docid": "#abc123",
                                    "title": "A采购合同",
                                    "score": 0.91,
                                    "snippet": "合同总价为人民币100万元。",
                                    "line": 12,
                                    "page_number": 3,
                                }
                            ]
                        }
                    }
                }
            ),
        ),
    ]

    results = QmdClient(url="http://localhost:8181/mcp").query("合同总价", ["company_docs"], 5)

    assert len(results) == 1
    assert results[0].file == "qmd://company_docs/contracts/a.md"
    assert results[0].docid == "#abc123"
    assert results[0].title == "A采购合同"
    assert results[0].score == 0.91
    assert results[0].snippet == "合同总价为人民币100万元。"
    assert results[0].line == 12
    assert results[0].page_number == 3
    assert FakeHttpxClient.calls[2]["json"]["params"] == {
        "name": "query",
        "arguments": {"query": "合同总价", "collections": ["company_docs"], "limit": 5},
    }
    assert FakeHttpxClient.calls[2]["headers"]["Mcp-Session-Id"] == "session-1"


def test_expected_response_rejects_empty_body_as_qmd_unavailable():
    FakeHttpxClient.responses = [
        FakeResponse(200, '{"result":{"protocolVersion":"2024-11-05"}}', {"mcp-session-id": "session-1"}),
        FakeResponse(202, ""),
        FakeResponse(200, ""),
    ]

    with pytest.raises(QmdUnavailable, match="empty response"):
        QmdClient(url="http://localhost:8181/mcp").status()


def test_expected_response_wraps_non_json_body_as_qmd_unavailable():
    FakeHttpxClient.responses = [
        FakeResponse(200, '{"result":{"protocolVersion":"2024-11-05"}}', {"mcp-session-id": "session-1"}),
        FakeResponse(202, ""),
        FakeResponse(200, "not-json"),
    ]

    with pytest.raises(QmdUnavailable, match="non-JSON response"):
        QmdClient(url="http://localhost:8181/mcp").status()

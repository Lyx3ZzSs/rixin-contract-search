import json

import pytest

from app.services.retrieval.qmd_client import QmdClient, QmdUnavailable, normalize_qmd_file


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        body: str = "",
        headers: dict[str, str] | None = None,
    ):
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
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "kwargs": self.kwargs}
        )
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def reset_fake_http_client(monkeypatch):
    import app.services.retrieval.qmd_client as qmd_client

    FakeHttpxClient.responses = []
    FakeHttpxClient.calls = []
    monkeypatch.setattr(qmd_client.httpx, "Client", FakeHttpxClient)


def test_normalize_qmd_file_rejects_path_escape():
    with pytest.raises(QmdUnavailable):
        normalize_qmd_file("qmd://company_docs/../secrets.pdf", "company_docs")


@pytest.mark.parametrize(
    "document_uri",
    [
        "qmd://company_docs/%2e%2e/secrets.pdf",
        "qmd://company_docs/%2e/contracts/a.md",
        "qmd:///contracts/a.md",
        "qmd://company_docs",
        "qmd://company_docs/contracts//a.md",
        "qmd://company_docs/contracts/%00a.md",
        "qmd://company_docs/contracts%5c..%5csecrets.pdf",
        "qmd://company_docs/contracts%2f..%2fsecrets.pdf",
    ],
)
def test_normalize_qmd_file_rejects_unsafe_decoded_uri_segments(document_uri):
    with pytest.raises(QmdUnavailable):
        normalize_qmd_file(document_uri, "company_docs")


def test_list_tools_uses_transport_session_and_filters_names():
    FakeHttpxClient.responses = [
        FakeResponse(
            200,
            '{"result":{"protocolVersion":"2024-11-05"}}',
            {"mcp-session-id": "session-1"},
        ),
        FakeResponse(202, ""),
        FakeResponse(
            200,
            json.dumps(
                {
                    "result": {
                        "tools": [
                            {"name": "doc_read"},
                            {"name": 123},
                            {"name": "doc_toc"},
                            {"not_name": "ignored"},
                            "not-a-dict",
                        ]
                    }
                }
            ),
        ),
    ]

    tools = QmdClient(url="http://localhost:8181/mcp").list_tools()

    assert tools == ["doc_read", "doc_toc"]
    assert FakeHttpxClient.calls[2]["json"]["method"] == "tools/list"
    assert FakeHttpxClient.calls[2]["json"]["params"] == {}
    assert FakeHttpxClient.calls[2]["headers"]["Mcp-Session-Id"] == "session-1"


@pytest.mark.parametrize(
    "response",
    [
        {"result": []},
        {"result": {}},
        {"result": {"tools": {}}},
    ],
)
def test_list_tools_rejects_invalid_response_shapes(monkeypatch, response):
    client = QmdClient(url="http://qmd.example/mcp")
    client._session_id = "session-1"

    monkeypatch.setattr(client, "_post", lambda payload: response)

    with pytest.raises(QmdUnavailable):
        client.list_tools()


def test_doc_read_calls_mcp_tool(monkeypatch):
    client = QmdClient(url="http://qmd.example/mcp")
    calls = []

    def fake_call_tool(name, arguments):
        calls.append((name, arguments))
        return {
            "structuredContent": {
                "text": "合同总价为人民币120万元",
                "page": 3,
                "anchor": "p3",
            }
        }

    monkeypatch.setattr(client, "_call_tool", fake_call_tool)

    payload = client.doc_read("qmd://company_docs/contracts/a.md", page=3, anchor=None, window=2)

    assert calls == [
        (
            "doc_read",
            {
                "document_uri": "qmd://company_docs/contracts/a.md",
                "page": 3,
                "anchor": None,
                "window": 2,
            },
        )
    ]
    assert payload["structuredContent"]["text"] == "合同总价为人民币120万元"


def test_document_preview_maps_structured_content(monkeypatch):
    client = QmdClient(url="http://qmd.example/mcp")

    def fake_call_tool(name, arguments):
        assert name == "doc_toc"
        return {
            "structuredContent": {
                "title": "A采购合同",
                "collection": "company_docs",
                "toc": [{"title": "第一章 合同标的", "page": 1}],
                "summary": "合同摘要",
                "open_url": "https://qmd.example/open/a",
                "download_url": "https://qmd.example/download/a",
            }
        }

    monkeypatch.setattr(client, "_call_tool", fake_call_tool)

    preview = client.document_preview("qmd://company_docs/contracts/a.md")

    assert preview == {
        "document_uri": "qmd://company_docs/contracts/a.md",
        "document_title": "A采购合同",
        "collection": "company_docs",
        "toc": [{"title": "第一章 合同标的", "page": 1}],
        "summary": "合同摘要",
        "can_open": True,
        "can_download": True,
        "open_url": "https://qmd.example/open/a",
        "download_url": "https://qmd.example/download/a",
    }


def test_document_preview_falls_back_to_text_content(monkeypatch):
    client = QmdClient(url="http://qmd.example/mcp")

    def fake_call_tool(name, arguments):
        assert name == "doc_toc"
        return {"content": [{"type": "text", "text": "第一章 合同标的\n第二章 价款"}]}

    monkeypatch.setattr(client, "_call_tool", fake_call_tool)

    preview = client.document_preview("qmd://company_docs/contracts/a.md")

    assert preview["document_uri"] == "qmd://company_docs/contracts/a.md"
    assert preview["summary"] == "第一章 合同标的\n第二章 价款"
    assert preview["can_download"] is False

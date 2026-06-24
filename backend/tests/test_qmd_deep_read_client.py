import pytest

from app.services.retrieval.qmd_client import QmdClient, QmdUnavailable, normalize_qmd_file


def test_normalize_qmd_file_rejects_path_escape():
    with pytest.raises(QmdUnavailable):
        normalize_qmd_file("qmd://company_docs/../secrets.pdf", "company_docs")


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

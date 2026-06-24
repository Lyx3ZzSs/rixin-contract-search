def test_qmd_document_preview_returns_preview_payload(client, monkeypatch):
    import app.api.qmd_documents as routes

    class FakeQmd:
        def document_preview(self, document_uri):
            return {
                "document_uri": document_uri,
                "document_title": "A合同",
                "collection": "company_docs",
                "toc": [{"title": "价款", "page": 3}],
                "summary": "价款章节",
                "can_open": False,
                "can_download": False,
            }

    monkeypatch.setattr(routes, "QmdClient", lambda: FakeQmd())

    response = client.get("/api/qmd-documents/preview?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md")

    assert response.status_code == 200
    assert response.json()["document_title"] == "A合同"


def test_qmd_document_download_unavailable_returns_clear_error(client, monkeypatch):
    import app.api.qmd_documents as routes

    class FakeQmd:
        def document_preview(self, document_uri):
            return {"document_uri": document_uri, "can_download": False}

    monkeypatch.setattr(routes, "QmdClient", lambda: FakeQmd())

    response = client.get("/api/qmd-documents/download?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "qmd_download_unavailable"

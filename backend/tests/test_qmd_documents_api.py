from app.models import AuditEvent


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


def test_qmd_document_redirect_rejects_hostile_targets(client, monkeypatch):
    import app.api.qmd_documents as routes

    cases = [
        ("open-link", "open_url", "https://evil.example/open/a", "qmd_preview_unavailable"),
        ("open-link", "open_url", "//evil.example/open/a", "qmd_preview_unavailable"),
        ("download", "download_url", "http://evil.example/download/a", "qmd_download_unavailable"),
        ("download", "download_url", "//evil.example/download/a", "qmd_download_unavailable"),
    ]

    for route, field, url, error_code in cases:
        def fake_qmd_factory(field_name=field, target_url=url):
            class FakeQmd:
                def document_preview(self, document_uri):
                    return {"document_uri": document_uri, field_name: target_url}

            return FakeQmd()

        monkeypatch.setattr(routes, "QmdClient", fake_qmd_factory)
        response = client.get(f"/api/qmd-documents/{route}?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == error_code


def test_qmd_document_redirect_audit_excludes_destination_urls(client, db_session, monkeypatch):
    import app.api.qmd_documents as routes

    session, _ = db_session

    class FakeQmd:
        def document_preview(self, document_uri):
            return {
                "document_uri": document_uri,
                "open_url": "/viewer?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md",
                "download_url": "/download/qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md",
            }

    monkeypatch.setattr(routes, "QmdClient", lambda: FakeQmd())

    response = client.get("/api/qmd-documents/open-link?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/viewer?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md"

    audit = session.query(AuditEvent).filter_by(event_type="document_opened").one()
    assert audit.payload == {"document_uri": "qmd://company_docs/contracts/a.md"}

    response = client.get("/api/qmd-documents/download?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/download/qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md"

    audit = session.query(AuditEvent).filter_by(event_type="document_downloaded").one()
    assert audit.payload == {"document_uri": "qmd://company_docs/contracts/a.md"}

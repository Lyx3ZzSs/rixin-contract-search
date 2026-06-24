from uuid import uuid4

from app.enums import ConditionVerdictValue, ResultDecision
from app.models import AuditEvent, ConditionVerdict, ScreeningDocumentResult, ScreeningTask


def _seed_task_with_result(session, *, owner_id: str = "internal-user", document_uri: str = "qmd://company_docs/contracts/a.md"):
    task = ScreeningTask(id=uuid4(), owner_id=owner_id, title="金额筛选", raw_query="金额大于100万", metrics={})
    session.add(task)
    session.flush()
    session.add(
        ScreeningDocumentResult(
            task_id=task.id,
            document_uri=document_uri,
            document_path="contracts/a.md",
            document_title="A合同",
            collection="company_docs",
            decision=ResultDecision.included.value,
            reason="condition_verdicts",
            matched_conditions=["amount"],
            missing_conditions=[],
            evidence=[],
            confidence=0.9,
        )
    )
    session.commit()
    return task


def _seed_task_with_verdict(session, *, owner_id: str = "internal-user", document_uri: str = "qmd://company_docs/contracts/a.md"):
    task = ScreeningTask(id=uuid4(), owner_id=owner_id, title="金额筛选", raw_query="金额大于100万", metrics={})
    session.add(task)
    session.flush()
    session.add(
        ConditionVerdict(
            task_id=task.id,
            document_uri=document_uri,
            condition_id="amount",
            verdict=ConditionVerdictValue.satisfied.value,
            confidence=0.9,
            supporting_evidence=[],
            contradicting_evidence=[],
            verification_method="grep_then_read",
        )
    )
    session.commit()
    return task


def test_qmd_document_preview_returns_preview_payload(client, db_session, monkeypatch):
    import app.api.qmd_documents as routes

    session, _ = db_session
    task = _seed_task_with_result(session)

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

    response = client.get(
        f"/api/qmd-documents/preview?task_id={task.id}&document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md"
    )

    assert response.status_code == 200
    assert response.json()["document_title"] == "A合同"


def test_qmd_document_download_unavailable_returns_clear_error(client, db_session, monkeypatch):
    import app.api.qmd_documents as routes

    session, _ = db_session
    task = _seed_task_with_result(session)

    class FakeQmd:
        def document_preview(self, document_uri):
            return {"document_uri": document_uri, "can_download": False}

    monkeypatch.setattr(routes, "QmdClient", lambda: FakeQmd())

    response = client.get(
        f"/api/qmd-documents/download?task_id={task.id}&document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "qmd_download_unavailable"


def test_qmd_document_preview_does_not_advertise_absolute_redirects(client, db_session, monkeypatch):
    import app.api.qmd_documents as routes

    session, _ = db_session
    task = _seed_task_with_result(session)

    class FakeQmd:
        def document_preview(self, document_uri):
            return {
                "document_uri": document_uri,
                "document_title": "A合同",
                "collection": "company_docs",
                "open_url": "https://evil.example/open/a",
                "download_url": "https://evil.example/download/a",
                "can_open": True,
                "can_download": True,
            }

    monkeypatch.setattr(routes, "QmdClient", lambda: FakeQmd())

    response = client.get(
        f"/api/qmd-documents/preview?task_id={task.id}&document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["can_open"] is False
    assert body["can_download"] is False

    audit = session.query(AuditEvent).filter_by(event_type="document_previewed").one()
    assert audit.payload["can_open"] is False
    assert audit.payload["can_download"] is False


def test_qmd_document_redirect_rejects_hostile_targets(client, db_session, monkeypatch):
    import app.api.qmd_documents as routes

    session, _ = db_session
    task = _seed_task_with_result(session)

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
        response = client.get(
            f"/api/qmd-documents/{route}?task_id={task.id}&document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md"
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == error_code


def test_qmd_document_redirect_audit_excludes_destination_urls(client, db_session, monkeypatch):
    import app.api.qmd_documents as routes

    session, _ = db_session
    task = _seed_task_with_result(session)

    class FakeQmd:
        def document_preview(self, document_uri):
            return {
                "document_uri": document_uri,
                "open_url": "/viewer?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md",
                "download_url": "/download/qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md",
            }

    monkeypatch.setattr(routes, "QmdClient", lambda: FakeQmd())

    response = client.get(
        f"/api/qmd-documents/open-link?task_id={task.id}&document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "/viewer?document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md"

    audit = session.query(AuditEvent).filter_by(event_type="document_opened").one()
    assert audit.payload == {"document_uri": "qmd://company_docs/contracts/a.md"}

    response = client.get(
        f"/api/qmd-documents/download?task_id={task.id}&document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "/download/qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md"

    audit = session.query(AuditEvent).filter_by(event_type="document_downloaded").one()
    assert audit.payload == {"document_uri": "qmd://company_docs/contracts/a.md"}


def test_qmd_document_preview_rejects_other_users_task(client, db_session, monkeypatch):
    import app.api.qmd_documents as routes

    session, _ = db_session
    task = _seed_task_with_result(session, owner_id="other-user")

    called = {"count": 0}

    class FakeQmd:
        def document_preview(self, document_uri):
            called["count"] += 1
            raise AssertionError("QmdClient should not be called for unauthorized tasks")

    monkeypatch.setattr(routes, "QmdClient", lambda: FakeQmd())

    response = client.get(
        f"/api/qmd-documents/preview?task_id={task.id}&document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert called["count"] == 0

    audit = session.query(AuditEvent).filter_by(event_type="permission_denied").one()
    assert audit.payload["resource_type"] == "screening_task"
    assert audit.payload["reason"] == "owner_mismatch"


def test_qmd_document_preview_rejects_unassociated_uri(client, db_session, monkeypatch):
    import app.api.qmd_documents as routes

    session, _ = db_session
    task = _seed_task_with_result(session, document_uri="qmd://company_docs/contracts/other.md")

    called = {"count": 0}

    class FakeQmd:
        def document_preview(self, document_uri):
            called["count"] += 1
            raise AssertionError("QmdClient should not be called for unassociated URIs")

    monkeypatch.setattr(routes, "QmdClient", lambda: FakeQmd())

    response = client.get(
        f"/api/qmd-documents/preview?task_id={task.id}&document_uri=qmd%3A%2F%2Fcompany_docs%2Fcontracts%2Fa.md"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert called["count"] == 0

import pytest

from app.api.auth import AuthContext, get_auth
from app.enums import AuditEventType
from app.main import app
from app.models import AgentEvalCase, AgentEvalRun, AuditEvent
from app.services.evals import compute_eval_metrics


def test_compute_eval_metrics_counts_precision_recall_and_support():
    cases = [
        {
            "expected": {"included": ["qmd://docs/a.md"], "excluded": ["qmd://docs/b.md"], "uncertain": ["qmd://docs/c.md"]},
            "actual": [
                {"document_uri": "qmd://docs/a.md", "decision": "included", "evidence_support_rate": 1.0, "verification_status": "deep_read_verified"},
                {"document_uri": "qmd://docs/b.md", "decision": "included", "evidence_support_rate": 0.0, "verification_status": "query_only"},
                {"document_uri": "qmd://docs/c.md", "decision": "uncertain", "evidence_support_rate": 0.0, "verification_status": "verification_failed"},
            ],
        }
    ]

    metrics = compute_eval_metrics(cases, schema_failures=1, verification_failures=1)

    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 1.0
    assert metrics["uncertain_rate"] == 1 / 3
    assert metrics["evidence_support_rate"] == 0.5
    assert metrics["schema_failure_rate"] == 1.0
    assert metrics["verification_failure_rate"] == 1.0


def test_compute_eval_metrics_ignores_duplicate_included_predictions():
    cases = [
        {
            "expected": {"included": ["qmd://docs/a.md"], "excluded": [], "uncertain": []},
            "actual": [
                {"document_uri": "qmd://docs/a.md", "decision": "included", "evidence_support_rate": 1.0, "verification_status": "deep_read_verified"},
                {"document_uri": "qmd://docs/a.md", "decision": "included", "evidence_support_rate": 0.8, "verification_status": "deep_read_verified"},
            ],
        }
    ]

    metrics = compute_eval_metrics(cases)

    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0


def test_compute_eval_metrics_clamps_negative_failure_counts():
    metrics = compute_eval_metrics([], schema_failures=-1, verification_failures=-2)

    assert metrics["schema_failure_rate"] == 0.0
    assert metrics["verification_failure_rate"] == 0.0


def test_compute_eval_metrics_clamps_failure_counts_to_case_count():
    cases = [
        {
            "expected": {"included": ["qmd://docs/a.md"], "excluded": [], "uncertain": []},
            "actual": [],
        }
    ]

    metrics = compute_eval_metrics(cases, schema_failures=5, verification_failures=5)

    assert metrics["schema_failure_rate"] == 1.0
    assert metrics["verification_failure_rate"] == 1.0


def test_agent_eval_run_endpoint_persists_metrics_and_cases(client, db_session):
    session, _ = db_session
    calls = {"count": 0}

    def override_auth():
        calls["count"] += 1
        return AuthContext(owner_id="test-owner")

    app.dependency_overrides[get_auth] = override_auth
    try:
        response = client.post(
            "/api/agent-evals/run",
            json={
                "cases": [
                    {
                        "name": "金额筛选",
                        "raw_query": "金额大于100万",
                        "expected": {"included": ["qmd://docs/a.md"], "excluded": [], "uncertain": []},
                        "actual": [{"document_uri": "qmd://docs/a.md", "decision": "included", "evidence_support_rate": 1.0, "verification_status": "deep_read_verified"}],
                    }
                ]
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["metrics"]["precision"] == 1.0
        assert body["metrics"]["recall"] == 1.0
        assert body["case_ids"]

        run = session.get(AgentEvalRun, body["run_id"])
        assert run is not None
        assert run.case_ids == body["case_ids"]
        assert len(run.case_ids) == 1

        stored_case_id = run.case_ids[0]
        stored_case = session.get(AgentEvalCase, stored_case_id)
        assert stored_case is not None
        assert stored_case.name == "金额筛选"
        assert stored_case.raw_query == "金额大于100万"
        assert stored_case.expected["expected"]["included"] == ["qmd://docs/a.md"]
        assert stored_case.expected["actual"][0]["decision"] == "included"

        audit = session.query(AuditEvent).filter_by(event_type=AuditEventType.agent_eval_run.value).one()
        assert audit.actor_id == "test-owner"
        assert audit.payload["run_id"] == body["run_id"]

        calls["count"] = 0
        get_response = client.get(f"/api/agent-evals/{body['run_id']}")

        assert get_response.status_code == 200
        assert calls["count"] == 1
    finally:
        app.dependency_overrides.pop(get_auth, None)


def test_agent_eval_run_endpoint_clamps_failure_counts(client):
    response = client.post(
        "/api/agent-evals/run",
        json={
            "cases": [
                {
                    "name": "金额筛选",
                    "raw_query": "金额大于100万",
                    "expected": {"included": ["qmd://docs/a.md"], "excluded": [], "uncertain": []},
                    "actual": [],
                }
            ],
            "schema_failures": 5,
            "verification_failures": 5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["schema_failure_rate"] == 1.0
    assert body["metrics"]["verification_failure_rate"] == 1.0


@pytest.mark.parametrize(
    "payload",
    [
        {
            "cases": [
                {
                    "name": "金额筛选",
                    "raw_query": "金额大于100万",
                    "expected": {"included": ["qmd://docs/a.md"], "excluded": [], "uncertain": []},
                    "actual": [{"document_uri": "   ", "decision": "included", "evidence_support_rate": 1.0, "verification_status": "deep_read_verified"}],
                }
            ]
        },
        {
            "cases": [
                {
                    "name": "金额筛选",
                    "raw_query": "金额大于100万",
                    "expected": {"included": ["   "], "excluded": [], "uncertain": []},
                    "actual": [{"document_uri": "qmd://docs/a.md", "decision": "included", "evidence_support_rate": 1.0, "verification_status": "deep_read_verified"}],
                }
            ]
        },
    ],
)
def test_agent_eval_run_rejects_empty_document_uris(client, payload):
    response = client.post("/api/agent-evals/run", json=payload)

    assert response.status_code == 422


def test_agent_eval_run_get_is_scoped_to_run_creator(client, db_session):
    session, _ = db_session

    def owner_override():
        return AuthContext(owner_id="owner-a")

    app.dependency_overrides[get_auth] = owner_override
    try:
        response = client.post(
            "/api/agent-evals/run",
            json={
                "cases": [
                    {
                        "name": "金额筛选",
                        "raw_query": "金额大于100万",
                        "expected": {"included": ["qmd://docs/a.md"], "excluded": [], "uncertain": []},
                        "actual": [{"document_uri": "qmd://docs/a.md", "decision": "included", "evidence_support_rate": 1.0, "verification_status": "deep_read_verified"}],
                    }
                ]
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run_id"]
    finally:
        app.dependency_overrides.pop(get_auth, None)

    app.dependency_overrides[get_auth] = lambda: AuthContext(owner_id="owner-b")
    try:
        scoped_response = client.get(f"/api/agent-evals/{run_id}")
    finally:
        app.dependency_overrides.pop(get_auth, None)

    assert scoped_response.status_code == 404
    assert scoped_response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("field", ["schema_failures", "verification_failures"])
def test_agent_eval_run_rejects_negative_failure_counts(client, field):
    payload = {
        "cases": [
            {
                "name": "金额筛选",
                "raw_query": "金额大于100万",
                "expected": {"included": ["qmd://docs/a.md"], "excluded": [], "uncertain": []},
                "actual": [{"document_uri": "qmd://docs/a.md", "decision": "included", "evidence_support_rate": 1.0, "verification_status": "deep_read_verified"}],
            }
        ],
        field: -1,
    }

    response = client.post("/api/agent-evals/run", json=payload)

    assert response.status_code == 422


def test_agent_eval_run_rejects_invalid_decision(client):
    response = client.post(
        "/api/agent-evals/run",
        json={
            "cases": [
                {
                    "name": "金额筛选",
                    "raw_query": "金额大于100万",
                    "expected": {"included": ["qmd://docs/a.md"], "excluded": [], "uncertain": []},
                    "actual": [{"document_uri": "qmd://docs/a.md", "decision": "maybe", "evidence_support_rate": 1.0, "verification_status": "deep_read_verified"}],
                }
            ]
        },
    )

    assert response.status_code == 422


def test_agent_eval_run_rejects_malformed_support_rate(client):
    response = client.post(
        "/api/agent-evals/run",
        json={
            "cases": [
                {
                    "name": "金额筛选",
                    "raw_query": "金额大于100万",
                    "expected": {"included": ["qmd://docs/a.md"], "excluded": [], "uncertain": []},
                    "actual": [{"document_uri": "qmd://docs/a.md", "decision": "included", "evidence_support_rate": "bad", "verification_status": "deep_read_verified"}],
                }
            ]
        },
    )

    assert response.status_code == 422

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


def test_agent_eval_run_endpoint_persists_metrics(client, db_session):
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

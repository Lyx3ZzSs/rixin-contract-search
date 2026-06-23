import csv
import io
from uuid import uuid4

from app.enums import ResultDecision, ReviewStatus, TaskStatus
from app.models import ScreeningDocumentResult, ScreeningPlan, ScreeningTask, StreamEvent


def seeded_export_task(session):
    task = ScreeningTask(
        id=uuid4(),
        owner_id="internal-user",
        title="GPU采购",
        raw_query="哪份合同采购了GPU服务器和存储服务器？",
        status=TaskStatus.completed.value,
        current_stage=TaskStatus.completed.value,
        progress_percent=100,
        metrics={"qmd_result_count": 3},
    )
    session.add(task)
    session.flush()
    session.add(ScreeningPlan(task_id=task.id, plan_json={"conditions": [{"id": "gpu", "description": "采购GPU服务器"}]}))
    session.add(
        ScreeningDocumentResult(
            task_id=task.id,
            document_uri="qmd://contract_docs/equipment-purchase-contract.md",
            document_path="equipment-purchase-contract.md",
            document_title="设备采购合同",
            collection="contract_docs",
            decision=ResultDecision.included.value,
            reason="Agent matched",
            matched_conditions=["gpu"],
            missing_conditions=[],
            evidence=[{"page": 1, "text": "GPU服务器 4台", "source": "qmd", "score": 0.93, "condition_id": "gpu", "artifact_ref": "qmd://contract_docs/equipment-purchase-contract.md"}],
            confidence=0.9,
            review_status=ReviewStatus.reviewed.value,
            review_decision=ResultDecision.included.value,
            review_note="人工确认",
            reviewer_name="张三",
        )
    )
    session.add(StreamEvent(task_id=task.id, sequence=1, event_type="task_created", payload={"task_id": str(task.id)}))
    session.commit()
    return task


def test_export_csv_contains_business_columns(client, db_session):
    session, _ = db_session
    task = seeded_export_task(session)

    response = client.get(f"/api/screening-tasks/{task.id}/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows[0]["task_title"] == "GPU采购"
    assert rows[0]["agent_decision"] == "included"
    assert rows[0]["review_decision"] == "included"
    assert rows[0]["reviewer_name"] == "张三"
    assert "GPU服务器 4台" in rows[0]["evidence_summary"]


def test_export_json_contains_task_plan_results_events(client, db_session):
    session, _ = db_session
    task = seeded_export_task(session)

    response = client.get(f"/api/screening-tasks/{task.id}/export.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["task_id"] == str(task.id)
    assert payload["plan"]["conditions"][0]["id"] == "gpu"
    assert payload["results"][0]["reviewer_name"] == "张三"
    assert payload["events"][0]["type"] == "task_created"


def test_export_xlsx_returns_excel_content_type(client, db_session):
    session, _ = db_session
    task = seeded_export_task(session)

    response = client.get(f"/api/screening-tasks/{task.id}/export.xlsx")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.content.startswith(b"PK")

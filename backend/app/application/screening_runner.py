from uuid import UUID

from app.config import settings
from app.db import SessionLocal, utcnow
from app.enums import AuditEventType, ResultDecision, TaskStatus
from app.models import ScreeningDocumentResult, ScreeningPlan, ScreeningTask
from app.schemas import ScreeningPlanPayload
from app.services.agent.aggregator import aggregate_document_candidates
from app.services.agent.classifier import classify_document
from app.services.agent.langgraph_agent import AgentExecutionError, ContractScreeningAgent
from app.services.agent.llm import AgentLlmConfigurationError, create_agent_llm
from app.services.agent.screening_plan import build_screening_plan
from app.services.audit import write_audit
from app.services.retrieval.qmd_client import QmdClient, QmdUnavailable, configured_collections, ensure_collections_available, persist_qmd_results
from app.services.streaming import append_stream_event


def run_screening_task(task_id: str) -> None:
    task_uuid = UUID(str(task_id))
    try:
        with SessionLocal() as session:
            task = session.get(ScreeningTask, task_uuid)
            if task is None or task.status != TaskStatus.uploaded.value:
                return
            task.status = TaskStatus.retrieving.value
            task.current_stage = TaskStatus.retrieving.value
            task.progress_percent = 10
            append_stream_event(session, task.id, "task_started", {"status": task.status})
            session.commit()
        retrieve_and_classify(task_uuid)
    except Exception as exc:
        mark_worker_unexpected(task_uuid, exc)


def retrieve_and_classify(task_id: UUID) -> None:
    with SessionLocal() as session:
        task = session.get(ScreeningTask, task_id)
        if task is None:
            return

        collections = configured_collections()
        qmd = QmdClient()
        try:
            agent = ContractScreeningAgent(
                llm=create_agent_llm(),
                qmd=qmd,
                collections=collections,
                top_k=settings.QMD_TOP_K,
                max_retrieval_rounds=settings.AGENT_MAX_RETRIEVAL_ROUNDS,
            )
            result = agent.run(session, task)
        except AgentLlmConfigurationError as exc:
            fail_task(session, task, exc.code, str(exc), "planning")
            session.commit()
            return
        except QmdUnavailable as exc:
            fail_task(session, task, "qmd_unavailable", str(exc), "retrieving")
            session.commit()
            return
        except AgentExecutionError as exc:
            fail_task(session, task, exc.code, str(exc), task.current_stage)
            session.commit()
            return

        task.status = TaskStatus.completed.value
        task.current_stage = TaskStatus.completed.value
        task.progress_percent = 100
        task.completed_at = utcnow()
        task.metrics = {**(task.metrics or {}), "qmd_result_count": result.qmd_result_count, "document_count": result.document_count}
        included = session.query(ScreeningDocumentResult).filter_by(task_id=task.id, decision=ResultDecision.included.value).count()
        uncertain = session.query(ScreeningDocumentResult).filter_by(task_id=task.id, decision=ResultDecision.uncertain.value).count()
        excluded = session.query(ScreeningDocumentResult).filter_by(task_id=task.id, decision=ResultDecision.excluded.value).count()
        append_stream_event(session, task.id, "task_completed", {"document_count": result.document_count, "included_count": included, "uncertain_count": uncertain, "excluded_count": excluded})
        session.commit()


def retrieve_candidates(session, task: ScreeningTask, plan: ScreeningPlanPayload, qmd: QmdClient, collections: list[str]) -> int:
    task.status = TaskStatus.retrieving.value
    task.current_stage = TaskStatus.retrieving.value
    task.progress_percent = 35
    total_candidates = 0
    fallback_collection = collections[0]
    for condition in plan.conditions:
        for query in condition.qmd_queries:
            append_stream_event(session, task.id, "qmd_searching", {"query_text": query, "condition_id": condition.id, "collections": collections})
            results = qmd.query(query, collections, settings.QMD_TOP_K)
            count = persist_qmd_results(session, task, condition.id, query, results, fallback_collection)
            total_candidates += count
            write_audit(session, AuditEventType.qmd_query.value, {"task_id": str(task.id), "condition_id": condition.id, "query_text": query, "candidate_count": count}, task=task)
            append_stream_event(session, task.id, "qmd_retrieved", {"query_text": query, "condition_id": condition.id, "candidate_count": count})
    return total_candidates


def classify_and_persist(session, task: ScreeningTask, plan: ScreeningPlanPayload) -> int:
    documents = aggregate_document_candidates(session, task.id, plan)
    total = max(1, len(documents))
    for index, document in enumerate(documents.values(), start=1):
        decision = classify_document(plan, document["conditions"])
        result = ScreeningDocumentResult(
            task_id=task.id,
            document_uri=document["document_uri"],
            document_path=document["document_path"],
            document_title=document["document_title"],
            collection=document["collection"],
            decision=decision["decision"].value,
            reason=decision["reason"],
            matched_conditions=decision["matched_conditions"],
            missing_conditions=decision["missing_conditions"],
            evidence=[item.model_dump() for item in decision["evidence"]],
            confidence=decision["confidence"],
        )
        session.add(result)
        write_audit(session, AuditEventType.classification_completed.value, {"task_id": str(task.id), "document_uri": result.document_uri, "decision": result.decision, "reason": result.reason, "confidence": result.confidence}, task=task)
        append_stream_event(session, task.id, "document_classified", {"document_uri": result.document_uri, "document_path": result.document_path, "decision": result.decision, "reason": result.reason})
        task.progress_percent = min(95, 80 + int(15 * index / total))
        append_stream_event(session, task.id, "progress", {"status": task.status, "progress_percent": task.progress_percent, "reviewed": index})
    return len(documents)


def fail_task(session, task: ScreeningTask, code: str, message: str, stage: str, details: dict | None = None) -> None:
    task.status = TaskStatus.failed.value
    task.current_stage = TaskStatus.failed.value
    task.error_code = code
    task.error_message = message
    task.completed_at = utcnow()
    payload = {"task_id": str(task.id), "stage": stage, "error_code": code, "message": message}
    if details:
        payload.update(details)
    write_audit(session, AuditEventType.task_failed.value, payload, task=task)
    append_stream_event(session, task.id, "task_failed", payload)


def mark_worker_unexpected(task_id: UUID, exc: Exception | None = None) -> None:
    with SessionLocal() as session:
        task = session.get(ScreeningTask, task_id)
        if task is None or task.status in {TaskStatus.completed.value, TaskStatus.failed.value}:
            return
        stage = task.current_stage
        details = None
        if exc is not None:
            details = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:300],
            }
        fail_task(session, task, "worker_unexpected_error", "Unexpected worker error", stage, details)
        session.commit()

from dataclasses import dataclass
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AuditEventType, ResultDecision, TaskStatus
from app.models import ScreeningDocumentResult, ScreeningPlan, ScreeningTask
from app.schemas import EvidenceItem, ScreeningPlanPayload
from app.services.agent.aggregator import aggregate_document_candidates
from app.services.agent.llm import AgentLlm
from app.services.audit import write_audit
from app.services.retrieval.qmd_client import ensure_collections_available, persist_qmd_results
from app.services.streaming import append_stream_event


class AgentExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class AgentRunResult:
    qmd_result_count: int
    document_count: int


class AgentState(TypedDict, total=False):
    session: Session
    task: ScreeningTask
    raw_query: str
    plan: ScreeningPlanPayload
    collections: list[str]
    retrieval_round: int
    qmd_result_count: int
    missing_condition_ids: list[str]
    should_refine: bool
    executed_queries: list[tuple[str, str]]
    document_count: int


class ContractScreeningAgent:
    def __init__(self, llm: AgentLlm, qmd: Any, collections: list[str], top_k: int, max_retrieval_rounds: int):
        self.llm = llm
        self.qmd = qmd
        self.collections = collections
        self.top_k = top_k
        self.max_retrieval_rounds = max_retrieval_rounds
        self.graph = self._build_graph()

    def run(self, session: Session, task: ScreeningTask) -> AgentRunResult:
        state = self.graph.invoke(
            {
                "session": session,
                "task": task,
                "raw_query": task.raw_query,
                "collections": self.collections,
                "retrieval_round": 0,
                "qmd_result_count": 0,
                "missing_condition_ids": [],
                "should_refine": False,
                "executed_queries": [],
                "document_count": 0,
            }
        )
        return AgentRunResult(qmd_result_count=int(state.get("qmd_result_count", 0)), document_count=int(state.get("document_count", 0)))

    def _build_graph(self):
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(AgentState)
        graph.add_node("plan", self._plan)
        graph.add_node("check_collections", self._check_collections)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("refine_queries", self._refine_queries)
        graph.add_node("classify", self._classify)
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "check_collections")
        graph.add_edge("check_collections", "retrieve")
        graph.add_conditional_edges("retrieve", self._route_after_retrieve, {True: "refine_queries", False: "classify"})
        graph.add_edge("refine_queries", "retrieve")
        graph.add_edge("classify", END)
        return graph.compile()

    def _plan(self, state: AgentState) -> AgentState:
        session = state["session"]
        task = state["task"]
        try:
            plan = self.llm.plan(state["raw_query"])
        except Exception as exc:
            raise AgentExecutionError("agent_plan_invalid", f"Unable to build screening plan: {exc}") from exc
        db_plan = ScreeningPlan(task_id=task.id, plan_json=plan.model_dump())
        session.add(db_plan)
        session.flush()
        append_stream_event(session, task.id, "criteria_parsed", {"plan_id": str(db_plan.id), "conditions": [{"id": c.id, "description": c.description} for c in plan.conditions]})
        return {**state, "plan": plan}

    def _check_collections(self, state: AgentState) -> AgentState:
        session = state["session"]
        task = state["task"]
        append_stream_event(session, task.id, "qmd_checking", {"collections": state["collections"]})
        ensure_collections_available(self.qmd.status(), state["collections"])
        task.progress_percent = 25
        return state

    def _retrieve(self, state: AgentState) -> AgentState:
        session = state["session"]
        task = state["task"]
        plan = state["plan"]
        collections = state["collections"]
        retrieval_round = int(state.get("retrieval_round", 0)) + 1
        task.progress_percent = 35
        fallback_collection = collections[0]
        added = 0
        executed = set(state.get("executed_queries", []))
        for condition in plan.conditions:
            for query in condition.qmd_queries:
                query_key = (condition.id, query)
                if query_key in executed:
                    continue
                append_stream_event(session, task.id, "qmd_searching", {"query_text": query, "condition_id": condition.id, "collections": collections, "round": retrieval_round})
                results = self.qmd.query(query, collections, self.top_k)
                executed.add(query_key)
                count = persist_qmd_results(session, task, condition.id, query, results, fallback_collection)
                added += count
                write_audit(session, AuditEventType.qmd_query.value, {"task_id": str(task.id), "condition_id": condition.id, "query_text": query, "candidate_count": count}, task=task)
                append_stream_event(session, task.id, "qmd_retrieved", {"query_text": query, "condition_id": condition.id, "candidate_count": count, "round": retrieval_round})
        missing = self._missing_condition_ids(session, task, plan)
        should_refine = bool(missing) and retrieval_round < self.max_retrieval_rounds
        return {
            **state,
            "retrieval_round": retrieval_round,
            "qmd_result_count": int(state.get("qmd_result_count", 0)) + added,
            "missing_condition_ids": missing,
            "should_refine": should_refine,
            "executed_queries": sorted(executed),
        }

    def _route_after_retrieve(self, state: AgentState) -> bool:
        return bool(state.get("should_refine"))

    def _refine_queries(self, state: AgentState) -> AgentState:
        session = state["session"]
        task = state["task"]
        plan = state["plan"]
        missing = state.get("missing_condition_ids", [])
        additions = self.llm.refine_queries(state["raw_query"], plan, missing)
        changed = False
        for condition in plan.conditions:
            existing = list(condition.qmd_queries)
            extra = [item.strip() for item in additions.get(condition.id, []) if item.strip()]
            merged = list(dict.fromkeys(existing + extra))
            if merged != existing:
                condition.qmd_queries = merged
                changed = True
        if changed:
            db_plan = session.scalars(select(ScreeningPlan).where(ScreeningPlan.task_id == task.id)).one()
            db_plan.plan_json = plan.model_dump()
        append_stream_event(session, task.id, "agent_refining_queries", {"missing_condition_ids": missing, "added": additions})
        return {**state, "plan": plan, "should_refine": False}

    def _classify(self, state: AgentState) -> AgentState:
        session = state["session"]
        task = state["task"]
        plan = state["plan"]
        task.status = TaskStatus.classifying.value
        task.current_stage = TaskStatus.classifying.value
        task.progress_percent = 75
        documents = aggregate_document_candidates(session, task.id, plan)
        total = max(1, len(documents))
        for index, document in enumerate(documents.values(), start=1):
            decision = self._validated_decision(plan, document)
            result = ScreeningDocumentResult(
                task_id=task.id,
                document_uri=str(document["document_uri"]),
                document_path=str(document["document_path"]),
                document_title=document["document_title"],
                collection=str(document["collection"]),
                decision=decision["decision"],
                reason=decision["reason"][:128],
                matched_conditions=decision["matched_conditions"],
                missing_conditions=decision["missing_conditions"],
                evidence=decision["evidence"][:10],
                confidence=decision["confidence"],
            )
            session.add(result)
            write_audit(session, AuditEventType.classification_completed.value, {"task_id": str(task.id), "document_uri": result.document_uri, "decision": result.decision, "reason": result.reason, "confidence": result.confidence}, task=task)
            append_stream_event(session, task.id, "document_classified", {"document_uri": result.document_uri, "document_path": result.document_path, "decision": result.decision, "reason": result.reason})
            task.progress_percent = min(95, 80 + int(15 * index / total))
            append_stream_event(session, task.id, "progress", {"status": task.status, "progress_percent": task.progress_percent, "reviewed": index})
        return {**state, "document_count": len(documents)}

    def _missing_condition_ids(self, session: Session, task: ScreeningTask, plan: ScreeningPlanPayload) -> list[str]:
        documents = aggregate_document_candidates(session, task.id, plan)
        condition_ids = {condition.id for condition in plan.conditions}
        matched = set()
        for document in documents.values():
            for condition_id, items in document["conditions"].items():
                if items:
                    matched.add(condition_id)
        return sorted(condition_ids - matched)

    def _validated_decision(self, plan: ScreeningPlanPayload, document: dict[str, Any]) -> dict[str, Any]:
        serializable_document = _serialize_document(document)
        try:
            raw = self.llm.classify_document(plan, serializable_document)
        except Exception as exc:
            raise AgentExecutionError("agent_classification_invalid", f"Unable to classify document: {exc}") from exc
        decision = str(raw.get("decision", ResultDecision.uncertain.value))
        if decision not in {item.value for item in ResultDecision}:
            decision = ResultDecision.uncertain.value
        all_condition_ids = [condition.id for condition in plan.conditions]
        matched = [str(item) for item in raw.get("matched_conditions", []) if str(item) in all_condition_ids]
        missing = [str(item) for item in raw.get("missing_conditions", []) if str(item) in all_condition_ids]
        evidence = []
        for item in raw.get("evidence", []):
            try:
                evidence.append(EvidenceItem(**item).model_dump())
            except Exception:
                continue
        if not evidence and decision != ResultDecision.excluded.value:
            decision = ResultDecision.uncertain.value
            matched = []
            missing = all_condition_ids
        return {
            "decision": decision,
            "reason": str(raw.get("reason") or "agent_decision"),
            "matched_conditions": matched,
            "missing_conditions": missing,
            "evidence": evidence,
            "confidence": max(0.0, min(1.0, float(raw.get("confidence", 0.0)))),
        }


def _serialize_document(document: dict[str, Any]) -> dict[str, Any]:
    conditions = {}
    for condition_id, items in document["conditions"].items():
        conditions[condition_id] = [item.model_dump() if hasattr(item, "model_dump") else item for item in items]
    return {
        "document_uri": document["document_uri"],
        "document_path": document["document_path"],
        "document_title": document["document_title"],
        "collection": document["collection"],
        "conditions": conditions,
    }

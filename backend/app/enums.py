from enum import StrEnum


class TaskStatus(StrEnum):
    uploaded = "uploaded"
    parsing = "parsing"
    parsed = "parsed"
    indexing = "indexing"
    indexed = "indexed"
    retrieving = "retrieving"
    classifying = "classifying"
    completed = "completed"
    failed = "failed"


class ParseStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    low_quality = "low_quality"
    failed = "failed"


class ResultDecision(StrEnum):
    included = "included"
    uncertain = "uncertain"
    excluded = "excluded"


class ReviewStatus(StrEnum):
    unreviewed = "unreviewed"
    reviewed = "reviewed"


class ConditionVerdictValue(StrEnum):
    satisfied = "satisfied"
    not_satisfied = "not_satisfied"
    unknown = "unknown"
    conflicting = "conflicting"


class ConditionType(StrEnum):
    amount = "amount"
    date = "date"
    party = "party"
    clause_presence = "clause_presence"
    clause_absence = "clause_absence"
    semantic_risk = "semantic_risk"
    keyword = "keyword"


class ConditionOperator(StrEnum):
    semantic_match = "semantic_match"
    gte = "gte"
    lte = "lte"
    eq = "eq"
    contains = "contains"
    not_contains = "not_contains"
    before = "before"
    after = "after"


class VerificationStrategy(StrEnum):
    query_only = "query_only"
    grep_then_read = "grep_then_read"
    doc_query = "doc_query"
    toc_guided_read = "toc_guided_read"


class VerificationStatus(StrEnum):
    query_only = "query_only"
    deep_read_verified = "deep_read_verified"
    partially_verified = "partially_verified"
    verification_failed = "verification_failed"


class UncertainReason(StrEnum):
    missing_evidence = "missing_evidence"
    conflicting_evidence = "conflicting_evidence"
    low_retrieval_confidence = "low_retrieval_confidence"
    ambiguous_requirement = "ambiguous_requirement"
    model_validation_failed = "model_validation_failed"
    verification_failed = "verification_failed"


class EvidenceRole(StrEnum):
    retrieval_candidate = "retrieval_candidate"
    supporting = "supporting"
    contradicting = "contradicting"
    missing_context = "missing_context"


class EvidenceSourceTool(StrEnum):
    query = "query"
    doc_grep = "doc_grep"
    doc_read = "doc_read"
    doc_query = "doc_query"
    doc_elements = "doc_elements"


class WorkerMode(StrEnum):
    simple = "simple"
    fork = "fork"


class ArtifactType(StrEnum):
    contract_markdown = "contract_markdown"
    page_markdown = "page_markdown"
    metadata_json = "metadata_json"
    evidence_json = "evidence_json"


class AuditEventType(StrEnum):
    task_created = "task_created"
    file_accepted = "file_accepted"
    parse_started = "parse_started"
    parse_succeeded = "parse_succeeded"
    parse_failed = "parse_failed"
    qmd_index_started = "qmd_index_started"
    qmd_index_completed = "qmd_index_completed"
    qmd_query = "qmd_query"
    qmd_mapping_failed = "qmd_mapping_failed"
    classification_completed = "classification_completed"
    result_reviewed = "result_reviewed"
    document_previewed = "document_previewed"
    document_opened = "document_opened"
    document_downloaded = "document_downloaded"
    agent_eval_run = "agent_eval_run"
    download = "download"
    permission_denied = "permission_denied"
    task_failed = "task_failed"

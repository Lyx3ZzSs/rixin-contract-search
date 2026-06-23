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
    download = "download"
    permission_denied = "permission_denied"
    task_failed = "task_failed"


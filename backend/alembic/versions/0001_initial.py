"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def uuid_type():
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "screening_tasks",
        sa.Column("id", uuid_type(), primary_key=True),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("raw_query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("current_stage", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_screening_tasks_owner_created", "screening_tasks", ["owner_id", "created_at"])
    op.create_index("ix_screening_tasks_owner_id", "screening_tasks", ["owner_id", "id"])
    op.create_index("ix_screening_tasks_status_created", "screening_tasks", ["status", "created_at"])

    op.create_table(
        "contract_files",
        sa.Column("id", uuid_type(), primary_key=True),
        sa.Column("task_id", uuid_type(), sa.ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("parse_status", sa.String(32), nullable=False),
        sa.Column("parse_quality", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contract_files_task", "contract_files", ["task_id"])
    op.create_index("ix_contract_files_owner_id", "contract_files", ["owner_id", "id"])
    op.create_index("ix_contract_files_sha256", "contract_files", ["sha256"])

    op.create_table(
        "parsed_artifacts",
        sa.Column("id", uuid_type(), primary_key=True),
        sa.Column("contract_id", uuid_type(), sa.ForeignKey("contract_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("parser_name", sa.String(128), nullable=False),
        sa.Column("parser_version", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("contract_id", "artifact_type", "page_number", name="uq_parsed_artifacts_contract_type_page"),
    )

    op.create_table(
        "screening_plans",
        sa.Column("id", uuid_type(), primary_key=True),
        sa.Column("task_id", uuid_type(), sa.ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "qmd_candidate_snippets",
        sa.Column("id", uuid_type(), primary_key=True),
        sa.Column("task_id", uuid_type(), sa.ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", uuid_type(), sa.ForeignKey("contract_files.id", ondelete="CASCADE"), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("condition_id", sa.String(64), nullable=False),
        sa.Column("snippet_text", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("artifact_ref", sa.Text(), nullable=True),
        sa.Column("qmd_docid", sa.String(128), nullable=True),
        sa.Column("raw_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_weak", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_qmd_candidates_task_condition", "qmd_candidate_snippets", ["task_id", "condition_id"])

    op.create_table(
        "contract_screening_results",
        sa.Column("id", uuid_type(), primary_key=True),
        sa.Column("task_id", uuid_type(), sa.ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", uuid_type(), sa.ForeignKey("contract_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(128), nullable=False),
        sa.Column("matched_conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("missing_conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "contract_id", name="uq_results_task_contract"),
    )
    op.create_index("ix_results_task_decision", "contract_screening_results", ["task_id", "decision"])

    op.create_table(
        "audit_events",
        sa.Column("id", uuid_type(), primary_key=True),
        sa.Column("task_id", uuid_type(), nullable=True),
        sa.Column("contract_id", uuid_type(), nullable=True),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_task_created", "audit_events", ["task_id", "created_at"])

    op.create_table(
        "stream_events",
        sa.Column("id", uuid_type(), primary_key=True),
        sa.Column("task_id", uuid_type(), sa.ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "sequence", name="uq_stream_events_task_sequence"),
    )
    op.create_index("ix_stream_events_task_sequence", "stream_events", ["task_id", "sequence"])


def downgrade() -> None:
    op.drop_table("stream_events")
    op.drop_table("audit_events")
    op.drop_table("contract_screening_results")
    op.drop_table("qmd_candidate_snippets")
    op.drop_table("screening_plans")
    op.drop_table("parsed_artifacts")
    op.drop_table("contract_files")
    op.drop_table("screening_tasks")

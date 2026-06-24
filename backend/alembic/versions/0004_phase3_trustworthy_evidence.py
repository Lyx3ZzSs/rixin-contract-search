"""phase3 trustworthy evidence

Revision ID: 0004_phase3_trustworthy_evidence
Revises: 0003_phase2_workbench
Create Date: 2026-06-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_phase3_trustworthy_evidence"
down_revision = "0003_phase2_workbench"
branch_labels = None
depends_on = None


def uuid_type():
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("screening_document_results", sa.Column("decision_basis", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("screening_document_results", sa.Column("uncertain_reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("screening_document_results", sa.Column("evidence_support_rate", sa.Float(), nullable=False, server_default="0"))
    op.add_column("screening_document_results", sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="query_only"))

    op.create_table(
        "condition_verdicts",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("task_id", uuid_type(), sa.ForeignKey("screening_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_uri", sa.Text(), nullable=False),
        sa.Column("condition_id", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("supporting_evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("contradicting_evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("missing_reason", sa.Text(), nullable=True),
        sa.Column("verification_method", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "document_uri", "condition_id", name="uq_condition_verdict_task_doc_condition"),
    )
    op.create_index("ix_condition_verdicts_task_document", "condition_verdicts", ["task_id", "document_uri"])

    op.create_table(
        "agent_eval_cases",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("raw_query", sa.Text(), nullable=False),
        sa.Column("expected", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_eval_runs",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("case_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("failures", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("agent_eval_runs")
    op.drop_table("agent_eval_cases")
    op.drop_index("ix_condition_verdicts_task_document", table_name="condition_verdicts")
    op.drop_table("condition_verdicts")
    op.drop_column("screening_document_results", "verification_status")
    op.drop_column("screening_document_results", "evidence_support_rate")
    op.drop_column("screening_document_results", "uncertain_reasons")
    op.drop_column("screening_document_results", "decision_basis")

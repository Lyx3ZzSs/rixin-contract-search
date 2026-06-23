"""add phase 2 review fields

Revision ID: 0003_phase2_workbench
Revises: 0002_doc_results
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_phase2_workbench"
down_revision = "0002_doc_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("screening_document_results", sa.Column("review_status", sa.String(length=32), nullable=False, server_default="unreviewed"))
    op.add_column("screening_document_results", sa.Column("review_decision", sa.String(length=32), nullable=True))
    op.add_column("screening_document_results", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("screening_document_results", sa.Column("reviewer_name", sa.String(length=128), nullable=True))
    op.add_column("screening_document_results", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_document_results_task_review", "screening_document_results", ["task_id", "review_status"])


def downgrade() -> None:
    op.drop_index("ix_document_results_task_review", table_name="screening_document_results")
    op.drop_column("screening_document_results", "reviewed_at")
    op.drop_column("screening_document_results", "reviewer_name")
    op.drop_column("screening_document_results", "review_note")
    op.drop_column("screening_document_results", "review_decision")
    op.drop_column("screening_document_results", "review_status")

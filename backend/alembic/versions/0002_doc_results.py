"""add document screening results

Revision ID: 0002_doc_results
Revises: 0001_initial
Create Date: 2026-06-22
"""

from alembic import op


revision = "0002_doc_results"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE qmd_candidate_snippets ADD COLUMN IF NOT EXISTS document_uri TEXT")
    op.execute("ALTER TABLE qmd_candidate_snippets ADD COLUMN IF NOT EXISTS document_path TEXT")
    op.execute("ALTER TABLE qmd_candidate_snippets ADD COLUMN IF NOT EXISTS document_title TEXT")
    op.execute("ALTER TABLE qmd_candidate_snippets ADD COLUMN IF NOT EXISTS collection VARCHAR(128)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS screening_document_results (
            id UUID PRIMARY KEY,
            task_id UUID NOT NULL REFERENCES screening_tasks(id) ON DELETE CASCADE,
            document_uri TEXT NOT NULL,
            document_path TEXT NOT NULL,
            document_title TEXT,
            collection VARCHAR(128) NOT NULL,
            decision VARCHAR(32) NOT NULL,
            reason VARCHAR(128) NOT NULL,
            matched_conditions JSONB NOT NULL,
            missing_conditions JSONB NOT NULL,
            evidence JSONB NOT NULL,
            confidence FLOAT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_document_results_task_document'
            ) THEN
                ALTER TABLE screening_document_results
                ADD CONSTRAINT uq_document_results_task_document
                UNIQUE (task_id, document_uri);
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_results_task_decision
        ON screening_document_results (task_id, decision)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS screening_document_results")
    op.execute("ALTER TABLE qmd_candidate_snippets DROP COLUMN IF EXISTS collection")
    op.execute("ALTER TABLE qmd_candidate_snippets DROP COLUMN IF EXISTS document_title")
    op.execute("ALTER TABLE qmd_candidate_snippets DROP COLUMN IF EXISTS document_path")
    op.execute("ALTER TABLE qmd_candidate_snippets DROP COLUMN IF EXISTS document_uri")

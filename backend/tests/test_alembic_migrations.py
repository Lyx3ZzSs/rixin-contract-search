from pathlib import Path


VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def test_document_screening_schema_lives_in_forward_migration():
    initial = (VERSIONS_DIR / "0001_initial.py").read_text()
    migration = VERSIONS_DIR / "0002_doc_results.py"

    assert migration.exists()
    migration_text = migration.read_text()

    assert '"screening_document_results"' not in initial
    assert '"document_uri"' not in initial
    assert "screening_document_results" in migration_text
    assert "document_uri" in migration_text
    assert "document_path" in migration_text
    assert "document_title" in migration_text
    assert "collection" in migration_text


def test_alembic_env_loads_project_dotenv_before_fallback_url():
    env_text = (Path(__file__).resolve().parents[1] / "alembic" / "env.py").read_text()

    assert "_load_project_dotenv()" in env_text
    assert "parents[2] / \".env\"" in env_text
    assert "os.environ.setdefault" in env_text

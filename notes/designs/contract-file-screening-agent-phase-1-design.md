# Technical Design: Contract File Screening Agent Phase 1

Status: engineering specification revised for enterprise unified parsing service; original `$eg-new-feature` hard gates passed on 2026-06-21.

Source PRD: `notes/prds/contract-file-screening-agent-2026-06-21.md`

This document is the implementation-grade Phase 1 design for a contract file screening Agent. It intentionally narrows the PRD into a deterministic vertical slice that can be implemented in one pass. No application code should be written until independent checks close with both `design ready` and `implementation ready`.

## 1. Goal

Build a web app that lets a user upload a small batch of contract files, enter a natural-language screening requirement, watch the backend pipeline progress in a streaming UI, and receive contract-file-level results with authenticated download links.

The product problem is file screening, not clause QA. The output unit is a contract file.

Phase 1 uses deterministic rules and fixture-friendly adapters so the product loop is runnable before production enterprise parsing-service and production qmd behavior are hardened.

## 1A. Parsing Boundary Decision

The contract screening Agent does not own or expose a production document parsing service.

The enterprise unified parsing service is the production document parsing provider. This project owns only:

- A `UnifiedParsingServiceAdapter` that submits files to the enterprise parsing service and normalizes responses.
- A stable internal `ParseResult` contract consumed by artifact writing, qmd indexing, evidence assembly, screening, audit, and frontend progress events.
- Evidence assembly and quality interpretation for the contract-screening workflow.
- Deterministic fake parser fixtures for local development and tests.

`paddleocr_service` and `fake_paddlex`-style services are not production architecture. They are development/test adapters or historical migration aids only. If a real OCR/PaddleOCR wrapper remains in the repository, it must not be required by the production Compose path after the enterprise unified parsing service is configured.

## 2. Current Repository State

The repository now contains a Phase 1 scaffold and implementation worktree, including backend, frontend, Compose, fake parser/OCR-related test doubles, and project notes. This document is the target engineering specification after the parsing-boundary decision: production document parsing is delegated to the enterprise unified parsing service, while this project owns adapter normalization, evidence assembly, screening, audit, and UI workflow.

Existing code may still contain migration-era names such as `paddlex_client.py`, `fake_paddlex`, or `paddleocr_service`. Those names are implementation debt relative to this revised design and should be renamed or isolated in follow-up implementation work.

## 3. Phase 1 Scope

### 3.1 In Scope

- FastAPI backend.
- React/Vite/TypeScript frontend.
- PostgreSQL, Redis, API, worker, and frontend through Docker Compose as optional deployment/manual-integration material.
- Optional enterprise unified parsing service integration through the parsing adapter.
- Upload 1 to 5 files per task.
- Supported uploads: `.pdf`, `.png`, `.jpg`, `.jpeg`.
- Persist original files under `STORAGE_ROOT`.
- Create one screening task per upload request.
- Parse files through a replaceable unified parsing service HTTP adapter.
- Provide a fake parser service for local Compose and API tests.
- Normalize enterprise parsing service responses into the internal `ParseResult` contract.
- Assemble contract-screening evidence, qmd documents, quality flags, and audit metadata inside this project.
- Write parser artifacts to disk as Markdown/JSON.
- Index/search through the qmd-compatible fixture adapter for Phase 1 acceptance.
- Document an optional qmd CLI adapter contract for later hardening; it is not part of Phase 1 acceptance.
- Generate a deterministic `ScreeningPlan` from the user query.
- Search qmd once per condition query.
- Group qmd snippets by `contract_id`.
- Classify each contract as `included` or `uncertain`.
- Keep `excluded` bucket present but empty in Phase 1.
- Stream business progress through authenticated fetch-based SSE.
- Render upload, progress, results, evidence drawer, and authenticated download in the frontend.
- Record minimal audit events.
- Add focused backend and frontend tests.

### 3.2 Out of Scope

- Production login, sessions, SSO, or organization RBAC.
- Multi-tenant permission matrix.
- Full task history page.
- Export XLSX/CSV/JSON.
- Human review/edit-decision endpoint.
- Automatic `excluded` classification.
- LLM classifier.
- Numeric/date/legal conclusion verification.
- DOCX/Excel/email ingestion.
- Production-grade qmd daemon management.
- Required qmd CLI runtime support.
- Owning, exposing, or operating a production OCR/document parsing service.
- Production PaddleOCR/PaddleX model orchestration.
- Maintaining two production parsing paths.
- Signed or expiring download links.

## 4. Technology Choices

### 4.1 Backend

- Python 3.12.
- FastAPI.
- Pydantic v2.
- SQLAlchemy 2 declarative ORM.
- Alembic.
- PostgreSQL 16 in Compose.
- SQLite only for isolated unit tests.
- Redis 7.
- RQ for background jobs.
- `httpx` for enterprise parsing service HTTP calls.
- `pypdf` for PDF validation/page count.
- `Pillow` for image validation.
- `pytest` plus FastAPI `TestClient`.

### 4.2 Frontend

- React.
- Vite.
- TypeScript.
- CSS modules or plain CSS files; no component library in Phase 1.
- Vitest.
- React Testing Library.

### 4.3 Runtime

- Local development verification runs through local Python/Node commands; Docker Compose is optional manual integration material.
- Backend and worker share the same backend image.
- Frontend uses Vite dev server in Compose.
- Fake parser is a small FastAPI service used only for local development and tests.

## 5. Repository Layout

```text
backend/
  Dockerfile
  .dockerignore
  pyproject.toml
  alembic.ini
  app/
    __init__.py
    main.py
    config.py
    db.py
    enums.py
    models.py
    schemas.py
    errors.py
    worker.py
    api/
      __init__.py
      auth.py
      screening_tasks.py
      contracts.py
    application/
      __init__.py
      screening_runner.py
      task_queue.py
    services/
      __init__.py
      storage.py
      audit.py
      streaming.py
      validation.py
      parsing/
        __init__.py
        unified_parser_client.py
        artifact_writer.py
      retrieval/
        __init__.py
        qmd_client.py
      agent/
        __init__.py
        screening_plan.py
        aggregator.py
        classifier.py
  alembic/
    env.py
    versions/
      0001_initial.py
  tests/
    conftest.py
    fixtures/
      parse_success.json
      parse_low_quality.json
      parse_nohit.json
      qmd_results.json
    test_upload_validation.py
    test_screening_plan.py
    test_aggregator.py
    test_classifier.py
    test_api_vertical_slice.py
    test_sse_events.py
    test_task_auth.py
    test_error_envelope.py
    test_download_auth.py
    test_unified_parser_client.py
    test_qmd_fixture.py
    qmd_cli_contract_optional.py
    test_operational_risks.py
    test_schema_migration.py

frontend/
  Dockerfile
  .dockerignore
  package.json
  package-lock.json
  index.html
  vite.config.ts
  playwright.config.ts
  tsconfig.json
  src/
    main.tsx
    App.tsx
    styles.css
    lib/
      api.ts
      sse.ts
      types.ts
    pages/
      UploadPage.tsx
      TaskProgressPage.tsx
    components/
      ProgressTimeline.tsx
      ResultBuckets.tsx
      ContractResultCard.tsx
      EvidenceDrawer.tsx
  tests/
    UploadPage.test.tsx
    TaskProgressPage.test.tsx
    sse.test.ts
    e2e/
      screening-flow.spec.ts

scripts/
  create_manual_samples.py

docker-compose.yml
.env.example
.gitignore
README.md
```

## 6. Environment

`.env.example` must contain exactly these keys and default values:

```text
DATABASE_URL=postgresql+psycopg://contract:contract@postgres:5432/contracts
TEST_DATABASE_URL=sqlite+pysqlite:///:memory:
REDIS_URL=redis://redis:6379/0
STORAGE_ROOT=/data/storage
APP_AUTH_TOKENS=dev-token:dev-user,other-token:other-user
PARSING_SERVICE_URL=
PARSING_SERVICE_API_KEY=
PARSING_SERVICE_PROVIDER=enterprise
QMD_MODE=fixture
QMD_BIN=qmd
QMD_INDEX_NAME=contracts
QMD_TOP_K=50
MAX_UPLOAD_MB=50
MAX_FILES_PER_TASK=5
MAX_PAGES_PER_FILE=200
SSE_KEEPALIVE_SECONDS=15
VITE_API_BASE_URL=http://localhost:8000
```

`backend/app/config.py` exposes a Pydantic settings object named `settings`. Tests may override these values with environment variables.

`backend/tests/conftest.py` must override `STORAGE_ROOT` to a per-test `tmp_path` before app/session fixtures are created. Default local pytest must never write to `/data/storage`.

Backend settings must set `model_config = SettingsConfigDict(env_file=".env", extra="ignore")` so frontend-only keys such as `VITE_API_BASE_URL` do not break API or worker startup.

Settings validation:

- `STORAGE_ROOT` must be an absolute path.
- `PARSING_SERVICE_URL` must be a non-empty HTTP or HTTPS URL.
- `PARSING_SERVICE_PROVIDER` must be one of `fake`, `enterprise`, or `custom`; Phase 1 local Compose defaults to `fake`, while production/staging should use `enterprise` or `custom`.
- `PARSING_SERVICE_API_KEY` may be empty for local fake parser but must not be logged when configured.
- Required Phase 1 settings validation accepts only `QMD_MODE=fixture`. `QMD_MODE=cli` is documented only as a future/reference adapter contract in section 17.2 and is rejected by shipped Phase 1 settings.
- `MAX_UPLOAD_MB`, `MAX_FILES_PER_TASK`, `MAX_PAGES_PER_FILE`, `QMD_TOP_K`, and `SSE_KEEPALIVE_SECONDS` must be positive integers.
- `MAX_FILES_PER_TASK` must equal `5` in Phase 1; it is configurable only so later phases can change it with tests and UI updates.
- `SSE_KEEPALIVE_SECONDS` must be between 1 and 300.

## 6A. Package Manifests

Lockfile policy:

- Frontend uses npm and must commit `frontend/package-lock.json`.
- Backend uses `pyproject.toml` plus compatible-version ranges; do not create or commit a Python lockfile in Phase 1.
- Docker images install from the backend package metadata and frontend npm lockfile.
- Manifest dependencies should use compatible-version ranges, not open-ended unpinned `*`.
- The first implementation runs `npm --prefix frontend install` once to generate `frontend/package-lock.json`; after that, all verification and Docker builds use `npm ci`.
- If npm dependency resolution fails, prefer the latest compatible patch/minor versions that satisfy npm peer dependencies and commit the resulting `package-lock.json`. It is acceptable to adjust React, Vite, router, TypeScript, Playwright, or Testing Library minor versions for installability, as long as app behavior and scripts stay the same.

`backend/pyproject.toml`:

```toml
[project]
name = "contract-screening-agent"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "alembic>=1.13,<2",
  "fastapi>=0.115,<1",
  "httpx>=0.27,<1",
  "pillow>=10,<12",
  "psycopg[binary]>=3.2,<4",
  "pydantic>=2.8,<3",
  "pydantic-settings>=2.4,<3",
  "pypdf>=4,<6",
  "python-multipart>=0.0.9,<1",
  "redis>=5,<7",
  "rq>=1.16,<3",
  "sqlalchemy>=2.0,<3",
  "uvicorn[standard]>=0.30,<1"
]

[build-system]
requires = ["setuptools>=70", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]

[project.optional-dependencies]
dev = [
  "pytest>=8,<9",
  "pytest-cov>=5,<7"
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

`frontend/package.json`:

```json
{
  "name": "contract-screening-agent-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest",
    "e2e": "playwright test"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.0.0",
    "@playwright/test": "^1.50.0",
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "jsdom": "^25.0.0",
    "typescript": "^5.0.0",
    "vite": "^6.0.0",
    "vitest": "^2.0.0"
  }
}
```

`frontend/tsconfig.json` must include app source, Vite config, Playwright config, and tests. It must set `types` to include `node`, `vitest/globals`, and `@testing-library/jest-dom` so `tsc -b`, Vitest, and Playwright all typecheck Node APIs such as `fileURLToPath` and `path.resolve`.

## 6B. FastAPI App Assembly

`backend/app/main.py`:

- Creates `app = FastAPI(title="Contract Screening Agent", version="0.1.0")`.
- Adds `CORSMiddleware`.
- Register `ApiAuthMiddleware` first, then register `CORSMiddleware` so CORS is the outermost middleware around auth and browser-visible 401 responses include CORS headers.
- `ApiAuthMiddleware` must explicitly pass through all `OPTIONS` requests without auth so browser CORS preflight is never rejected for missing bearer tokens.
- Allows origins:
  - `http://localhost:5173`
  - `http://127.0.0.1:5173`
- Allows methods `["GET", "POST", "OPTIONS"]`.
- Allows headers `["Authorization", "Content-Type", "Last-Event-ID"]`.
- Exposes `GET /healthz` returning `{"status":"ok"}` without auth.
- Mounts routers:
  - `screening_tasks.router` at `/api/screening-tasks`.
  - `contracts.router` at `/api/contracts`.

`backend/app/db.py`:

- Exposes `engine`, `SessionLocal`, `Base`, and `get_session()`.
- `get_session()` is a FastAPI dependency yielding a SQLAlchemy session.
- Tests override `get_session()` with an in-memory SQLite session.
- SQLite tests must create the engine with `connect_args={"check_same_thread": False}` and `poolclass=StaticPool` so FastAPI `TestClient`, direct service calls, and synchronous worker execution share the same in-memory schema/data.
- Defines `GUID`, a SQLAlchemy `TypeDecorator`:
  - PostgreSQL uses `UUID(as_uuid=True)`.
  - SQLite and other dialects use `CHAR(36)`.
  - Bound values accept `uuid.UUID` or UUID strings and return `uuid.UUID`.
- Defines `utcnow()` returning timezone-aware UTC `datetime`.
- Model timestamp defaults use Python-side `default=utcnow` and `onupdate=utcnow`; Alembic migration does not rely on database `now()` defaults.
- JSON columns use SQLAlchemy `JSON` in models. Alembic may use PostgreSQL `JSONB` for Postgres, while SQLite tests use SQLAlchemy JSON/text compatibility.

`backend/app/enums.py` owns and exports `TaskStatus`, `ParseStatus`, `ResultDecision`, `ArtifactType`, and `AuditEventType`. Models, schemas, services, and tests import enum classes from this module.

`backend/alembic/env.py`:

- Imports `Base.metadata` from `app.db`.
- Imports `app.models` before setting `target_metadata`.
- Reads database URL from `DATABASE_URL`.

`backend/app/errors.py`:

- Defines `ApiError(code: str, message: str, status_code: int, details: dict[str, Any] | None = None)`.
- Registers a FastAPI exception handler that returns the error envelope.
- Registers handlers for FastAPI/Starlette `HTTPException`, unmatched routes, and method-not-allowed responses so they return the same envelope rather than FastAPI's default `{"detail": ...}` shape.

## 6C. Backend Pydantic Schemas

`backend/app/schemas.py` must define these public schemas:

```python
class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

class ErrorEnvelope(BaseModel):
    error: ErrorBody

class CreateTaskResponse(BaseModel):
    task_id: UUID
    title: str
    raw_query: str
    status: TaskStatus
    progress_percent: int
    events_url: str
    results_url: str

class TaskCounts(BaseModel):
    files: int
    parsed: int
    parse_failed: int
    low_quality: int
    included: int
    uncertain: int
    excluded: int

class TaskSummaryResponse(BaseModel):
    task_id: UUID
    title: str
    raw_query: str
    status: TaskStatus
    progress_percent: int
    current_stage: str
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    counts: TaskCounts

class EvidenceItem(BaseModel):
    page: int | None = None
    text: str
    source: Literal["qmd"] = "qmd"
    score: float | None = None
    condition_id: str
    artifact_ref: str | None = None

class ContractResultItem(BaseModel):
    contract_id: UUID
    file_name: str
    download_url: str
    decision: ResultDecision
    reason: str
    matched_conditions: list[str]
    missing_conditions: list[str]
    evidence: list[EvidenceItem]
    confidence: float
    parse_status: ParseStatus
    file_size_bytes: int
    created_at: datetime
    updated_at: datetime

class ResultBuckets(BaseModel):
    included: list[ContractResultItem]
    uncertain: list[ContractResultItem]
    excluded: list[ContractResultItem]

class TaskResultsResponse(BaseModel):
    task_id: UUID
    buckets: ResultBuckets

class StreamEventEnvelope(BaseModel):
    event_id: str
    type: str
    task_id: UUID
    timestamp: datetime
    payload: dict[str, Any]

class ScreeningCondition(BaseModel):
    id: str
    description: str
    operator: Literal["semantic_match"]
    value: str
    qmd_queries: list[str]
    evidence_required: int = 1
    structured: bool

class ScreeningPlanPayload(BaseModel):
    target: Literal["contract_file"]
    conditions: list[ScreeningCondition]
    decision_policy: Literal["phase1_keyword_candidate_uncertain_on_structured_comparison"]

class ContractScreeningDecision(BaseModel):
    contract_id: UUID
    decision: ResultDecision
    reason: str
    matched_conditions: list[str]
    missing_conditions: list[str]
    evidence: list[EvidenceItem]
    confidence: float
```

Pydantic should serialize UUIDs and datetimes to strings through default JSON behavior. Do not use field aliases in Phase 1.

## 7. Domain Enums

Use string enums in Pydantic and SQLAlchemy.

```text
TaskStatus:
  uploaded
  parsing
  parsed
  indexing
  indexed
  retrieving
  classifying
  completed
  failed

ParseStatus:
  pending
  running
  succeeded
  low_quality
  failed

ResultDecision:
  included
  uncertain
  excluded

ArtifactType:
  contract_markdown
  page_markdown
  metadata_json
  evidence_json

AuditEventType:
  task_created
  file_accepted
  parse_started
  parse_succeeded
  parse_failed
  qmd_index_started
  qmd_index_completed
  qmd_query
  qmd_mapping_failed
  classification_completed
  download
  permission_denied
  task_failed
```

`ResultDecision.excluded` exists for schema compatibility but is never assigned by the Phase 1 classifier.

## 8. Database Schema

Use app-side UTC timestamps. PostgreSQL migrations use UUID columns. SQLite tests use string UUIDs through a portable SQLAlchemy type helper.

### 8.1 `screening_tasks`

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | UUID PK | no | Generated by app. |
| `owner_id` | varchar(128) | no | From token map. |
| `title` | varchar(120) | no | Defaults to first 40 query chars. |
| `raw_query` | text | no | Max 1000 chars enforced by API. |
| `status` | varchar(32) | no | `TaskStatus`. |
| `progress_percent` | integer | no | 0 to 100. |
| `current_stage` | varchar(64) | no | Human-readable stage key. |
| `error_code` | varchar(64) | yes | From error codes. |
| `error_message` | text | yes | Safe user-facing message. |
| `metrics` | JSON | no | Default `{}`. |
| `created_at` | timestamptz | no | UTC. |
| `updated_at` | timestamptz | no | UTC. |
| `completed_at` | timestamptz | yes | UTC. |

Indexes:

- `(owner_id, created_at)`
- `(owner_id, id)`
- `(status, created_at)`

### 8.2 `contract_files`

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | UUID PK | no | Contract ID. |
| `task_id` | UUID FK `screening_tasks.id` | no | Cascade delete. |
| `owner_id` | varchar(128) | no | Denormalized for auth checks. |
| `original_filename` | varchar(255) | no | Sanitized basename for display. |
| `stored_path` | text | no | Absolute path under `STORAGE_ROOT`. |
| `content_type` | varchar(128) | no | Validated MIME. |
| `sha256` | char(64) | no | Hex digest. |
| `file_size_bytes` | bigint | no | Must be > 0. |
| `page_count` | integer | yes | PDF/image pages from validation or parser. |
| `parse_status` | varchar(32) | no | `ParseStatus`, default `pending`. |
| `parse_quality` | JSON | no | Default `{}`. |
| `created_at` | timestamptz | no | UTC. |
| `updated_at` | timestamptz | no | UTC. |

Indexes:

- `(task_id)`
- `(owner_id, id)`
- `(sha256)`

### 8.3 `parsed_artifacts`

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | UUID PK | no | Generated by app. |
| `contract_id` | UUID FK `contract_files.id` | no | Cascade delete. |
| `artifact_type` | varchar(64) | no | `ArtifactType`. |
| `page_number` | integer | no | Use `0` for contract-level artifacts; page artifacts use positive page number. |
| `stored_path` | text | no | Absolute path under `STORAGE_ROOT`. |
| `parser_name` | varchar(128) | no | From normalized `ParseResult`. |
| `parser_version` | varchar(128) | no | From normalized `ParseResult`. |
| `created_at` | timestamptz | no | UTC. |

Unique constraints:

- `(contract_id, artifact_type, page_number)`

Because contract-level artifacts use `page_number=0`, this unique constraint prevents duplicate `contract_markdown`, `metadata_json`, and `evidence_json` rows on PostgreSQL and SQLite.

### 8.4 `screening_plans`

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | UUID PK | no | Generated by app. |
| `task_id` | UUID FK `screening_tasks.id` | no | Unique. |
| `plan_json` | JSON | no | Shape in section 18. |
| `created_at` | timestamptz | no | UTC. |

### 8.5 `qmd_candidate_snippets`

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | UUID PK | no | Generated by app. |
| `task_id` | UUID FK `screening_tasks.id` | no | Cascade delete. |
| `contract_id` | UUID FK `contract_files.id` | yes | Null if mapping failed. |
| `query_text` | text | no | qmd query. |
| `condition_id` | varchar(64) | no | From plan. |
| `snippet_text` | text | no | Result snippet/body preview. |
| `page_number` | integer | yes | Parsed from marker if available. |
| `qmd_score` | float | yes | 0 to 1 when qmd returns score. |
| `qmd_docid` | varchar(128) | yes | qmd docid such as `#abc123`. |
| `artifact_ref` | text | yes | Logical `qmd://` or `artifact://` reference only; never a filesystem path. |
| `raw_result` | JSON | no | Original qmd item. |
| `created_at` | timestamptz | no | UTC. |

Indexes:

- `(task_id, condition_id)`
- `(contract_id)`

### 8.6 `contract_screening_results`

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | UUID PK | no | Generated by app. |
| `task_id` | UUID FK `screening_tasks.id` | no | Cascade delete. |
| `contract_id` | UUID FK `contract_files.id` | no | Cascade delete. |
| `decision` | varchar(32) | no | `ResultDecision`. |
| `reason` | varchar(128) | no | Reason code. |
| `matched_conditions` | JSON | no | Array of condition IDs. |
| `missing_conditions` | JSON | no | Array of condition IDs. |
| `evidence` | JSON | no | Array shape in section 19. |
| `confidence` | float | no | 0 to 1. |
| `created_at` | timestamptz | no | UTC. |
| `updated_at` | timestamptz | no | UTC. |

Unique constraints:

- `(task_id, contract_id)`

### 8.7 `audit_events`

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | UUID PK | no | Generated by app. |
| `task_id` | UUID FK `screening_tasks.id` | yes | Nullable for auth failures before task known. |
| `contract_id` | UUID FK `contract_files.id` | yes | Nullable. |
| `actor_id` | varchar(128) | yes | Null only if no actor can be known; Phase 1 invalid-token requests create no audit row, and worker/system audits use the task `owner_id`. |
| `event_type` | varchar(64) | no | `AuditEventType`. |
| `payload` | JSON | no | Default `{}`. No local file paths. |
| `created_at` | timestamptz | no | UTC. |

Indexes:

- `(task_id, created_at)`
- `(actor_id, created_at)`
- `(event_type, created_at)`

### 8.8 `stream_events`

| Column | Type | Nullable | Notes |
| --- | --- | --- | --- |
| `id` | UUID PK | no | Generated by app. |
| `task_id` | UUID FK `screening_tasks.id` | no | Cascade delete. |
| `sequence` | integer | no | Starts at 1 per task. |
| `event_type` | varchar(64) | no | SSE event type. |
| `payload` | JSON | no | Event-specific payload. |
| `created_at` | timestamptz | no | UTC. |

Unique constraints:

- `(task_id, sequence)`

Indexes:

- `(task_id, sequence)`

## 8A. Audit Payloads

`audit_events.payload` is a JSON object. It must not include `stored_path`, local artifact paths, raw full contract text, or bearer tokens.

Payloads by event type:

| Event type | Required payload fields |
| --- | --- |
| `task_created` | `task_id`, `title`, `file_count` |
| `file_accepted` | `task_id`, `contract_id`, `file_name`, `file_size_bytes`, `content_type`, `sha256` |
| `parse_started` | `task_id`, `contract_id`, `file_name` |
| `parse_succeeded` | `task_id`, `contract_id`, `parse_status`, `page_count`, `quality` |
| `parse_failed` | `task_id`, `contract_id`, `error_code`, `message` |
| `qmd_index_started` | `task_id`, `collection_name`, `contract_count` |
| `qmd_index_completed` | `task_id`, `collection_name`, `indexed_count` |
| `qmd_query` | `task_id`, `condition_id`, `query_text`, `candidate_count` |
| `qmd_mapping_failed` | `task_id`, `condition_id`, `artifact_ref`, `reason` |
| `classification_completed` | `task_id`, `contract_id`, `decision`, `reason`, `confidence` |
| `download` | `task_id`, `contract_id`, `file_name` |
| `permission_denied` | `resource_type`, `resource_id`, `reason` |
| `task_failed` | `task_id`, `stage`, `error_code`, `message` |

Actor rules:

- Request-originated audit events use `AuthContext.owner_id`.
- Worker-originated audit events, including parse, qmd, classification, and task failure events, use `screening_tasks.owner_id`.
- Invalid-token requests create no audit events.

Manual audit verification may use this root-level command while Compose is running:

```sh
docker compose exec postgres psql -U contract -d contracts -c "select event_type, payload->>'file_name' as file_name from audit_events order by created_at desc limit 10;"
```

`permission_denied` payload values:

- Cross-owner task summary/events/results: `resource_type="screening_task"`, `resource_id="{task_id}"`, `reason="owner_mismatch"`.
- Cross-owner contract download: `resource_type="contract_file"`, `resource_id="{contract_id}"`, `reason="owner_mismatch"`.
- Download path escape: `resource_type="contract_file"`, `resource_id="{contract_id}"`, `reason="path_escape"`.

## 9. API Auth

Phase 1 uses static bearer tokens from `APP_AUTH_TOKENS`.

Parsing:

- Split config on commas.
- The full config string after trimming must be non-empty.
- Empty comma segments are malformed, including leading comma, trailing comma, `,,`, and whitespace-only segments.
- Each non-empty segment must contain exactly one colon and is parsed as `token:owner_id`; examples such as `a:b:c`, `tokenonly`, and `:owner` are malformed.
- Token and owner ID must be non-empty after trimming.
- Token and owner ID must each be at most 128 characters after trimming; longer values are startup configuration errors.
- Duplicate token is startup configuration error.
- Duplicate owner ID is allowed.

Request rules:

- All `/api/*` routes except CORS preflight `OPTIONS` require `Authorization: Bearer <token>`.
- Missing header returns `401 auth_invalid`.
- Non-bearer header returns `401 auth_invalid`.
- Unknown token returns `401 auth_invalid`.
- Valid token accessing a resource owned by another owner returns `404 not_found`, not `403`, to avoid resource existence leakage.
- For valid-token cross-owner access where the resource exists, write `permission_denied` audit before returning `404`.
- Invalid-token requests do not create audit events because no actor is known.
- Auth is enforced before route body parsing by `ApiAuthMiddleware` mounted in `backend/app/main.py` for paths starting with `/api/`.
- `ApiAuthMiddleware` passes through `OPTIONS` requests without auth, validates the `Authorization` header for all other `/api/*` requests, returns the standard error envelope directly on `auth_invalid`, and stores `AuthContext` on `request.state.auth` before `call_next`.
- Upload route handlers must accept `Request` and call `await request.form()` only after reading `request.state.auth`; they must not declare required `File(...)` or `Form(...)` parameters that can trigger multipart parsing before auth.

`backend/app/api/auth.py` exposes:

```python
class AuthContext(BaseModel):
    token: str
    owner_id: str

class ApiAuthMiddleware(BaseHTTPMiddleware): ...

def get_auth_context(request: Request) -> AuthContext
```

## 10. Error Envelope

All API errors use this shape:

```json
{
  "error": {
    "code": "file_empty",
    "message": "Human readable message",
    "details": {}
  }
}
```

Known error codes:

```text
auth_invalid -> 401
not_found -> 404
internal_error -> 500
invalid_request -> 422
query_required -> 400
query_too_long -> 400
title_too_long -> 400
file_empty -> 400
too_many_files -> 400
file_too_large -> 413
unsupported_file_type -> 400
invalid_pdf -> 400
invalid_image -> 400
too_many_pages -> 400
enqueue_failed -> 503
qmd_command_failed -> task failure, not direct API failure
parse_all_failed -> task failure, not direct API failure
task_stale -> task failure, not direct API failure
parse_service_rejected -> file parse failure
parse_service_unavailable -> file parse failure
parse_service_timeout -> file parse failure
parse_service_invalid_response -> file parse failure
storage_write_failed -> 500 during upload before task creation; not a worker task failure
artifact_write_failed -> task failure, not direct API failure
download_file_missing -> 404
download_file_unreadable -> 404
```

`details` must be an object. It may include safe metadata such as `filename`, `limit`, `actual`, or `stage`, but never `stored_path`.

Unexpected unhandled backend exceptions return `500 internal_error` with message `系统错误，请稍后重试` and `details={}`. The server may log stack traces, but the API response must not expose exception text, file paths, SQL, query text, bearer tokens, or contract text.

Validation mapping:

- Missing `query`: `400 query_required`, message `筛选条件不能为空`.
- Blank trimmed `query`: `400 query_required`, message `筛选条件不能为空`.
- `query` longer than 1000 characters after trimming: `400 query_too_long`, message `筛选条件不能超过1000个字符`.
- `title` longer than 120 characters after trimming: `400 title_too_long`, message `标题不能超过120个字符`.
- Missing `files`: `400 file_empty`, message `请至少上传一个合同文件`.
- Malformed UUID path parameter: `422 invalid_request`, message `请求参数格式错误`.
- Malformed multipart body: `422 invalid_request`, message `请求格式错误`.
- Other FastAPI request validation errors: `422 invalid_request`, message `请求参数格式错误`.

FastAPI `RequestValidationError` must be converted into this envelope. Do not return FastAPI's default validation response.

FastAPI/Starlette `HTTPException` mapping:

- `404`: `404 not_found`, message `资源不存在`.
- `405`: `422 invalid_request`, message `请求参数格式错误`.
- Other HTTP exceptions: preserve the HTTP status when possible, use `invalid_request` for 4xx and `internal_error` for 5xx, and never expose raw `detail` values unless they are one of the known safe messages in this section.

Default user-facing API messages:

| Error code | Message |
| --- | --- |
| `auth_invalid` | `认证失败，请重新登录` |
| `not_found` | `资源不存在` |
| `file_empty` | `请至少上传一个合同文件` |
| `too_many_files` | `单次最多上传5个文件` |
| `file_too_large` | `文件大小超过限制` |
| `unsupported_file_type` | `不支持的文件类型` |
| `invalid_pdf` | `PDF文件无效或无法读取` |
| `invalid_image` | `图片文件无效或无法读取` |
| `too_many_pages` | `PDF页数超过限制` |
| `storage_write_failed` | `文件保存失败` |
| `download_file_missing` | `文件不存在或已被移除` |
| `download_file_unreadable` | `文件无法读取` |
| `enqueue_failed` | `筛选任务启动失败` |
| `invalid_request` | `请求参数格式错误` |

## 11. Backend API

All response timestamps are ISO 8601 UTC strings.

### 11.1 `POST /api/screening-tasks`

Creates a screening task and enqueues the worker.

Request:

- Content type: `multipart/form-data`.
- Field `query`: required string, trimmed, length 1 to 1000.
- Field `title`: optional string, trimmed, max 120.
- Field `files`: required repeated upload field, 1 to 5 files.

Title defaulting:

- If `title` is absent, default to the first 40 Unicode characters of trimmed `query`.
- If `title` is present but trims to an empty string, use the same default.
- If `title` trims to more than 120 characters, reject with `title_too_long`.

Validation is all-or-nothing. If any file fails validation, no database rows remain and any temporary files are removed.

Success status: `201`.

Response:

```json
{
  "task_id": "7b6e8894-1d51-4b30-8a91-134d738aa51c",
  "title": "金额大于100万的合同",
  "raw_query": "金额大于100万的合同",
  "status": "uploaded",
  "progress_percent": 5,
  "events_url": "/api/screening-tasks/7b6e8894-1d51-4b30-8a91-134d738aa51c/events",
  "results_url": "/api/screening-tasks/7b6e8894-1d51-4b30-8a91-134d738aa51c/results"
}
```

Side effects on success:

- Create `screening_tasks`.
- Create one `contract_files` row per accepted file.
- Copy uploaded files to storage.
- Create `task_created` stream event.
- Create `file_accepted` stream event per file.
- Write matching audit events.
- Enqueue `run_screening_task(str(task_id))`.

Transaction boundary:

1. Validate all uploaded files into temporary files outside final storage.
2. Open a DB transaction.
3. Insert task, contract rows, stream events, and audit events.
4. Move temp files into final storage before committing.
5. Commit the DB transaction.
6. Enqueue the RQ job after commit so the worker can see committed rows.
7. If file move fails before commit, roll back the transaction, delete temp/final files from the request, and return `500 storage_write_failed`.
8. If DB commit raises after final files have been moved, do not delete final files because commit outcome can be ambiguous. Return `500 storage_write_failed`; any files left on disk are audit-only residue under the task storage path and are not exposed unless rows actually committed.

If RQ enqueue fails after rows/files are created:

- Open a new transaction.
- Set task `status=failed`, `error_code=enqueue_failed`, `error_message="Unable to enqueue screening task"`, `completed_at=now`.
- Emit `task_failed`.
- Commit the failure state.
- Return `503 enqueue_failed` using the standard error envelope. Do not include `task_id` in the response and do not navigate the frontend to a task page; the user sees an enqueue error and may retry upload.
- Keep the failed task rows and uploaded files as audit-only residue for operator debugging in Phase 1. They remain inaccessible from the frontend because task history is out of scope.

### 11.2 `GET /api/screening-tasks/{task_id}`

Returns task summary for polling fallback.

Success status: `200`.

Response:

```json
{
  "task_id": "7b6e8894-1d51-4b30-8a91-134d738aa51c",
  "title": "金额大于100万的合同",
  "raw_query": "金额大于100万的合同",
  "status": "classifying",
  "progress_percent": 75,
  "current_stage": "classifying",
  "error_code": null,
  "error_message": null,
  "created_at": "2026-06-21T10:00:00Z",
  "updated_at": "2026-06-21T10:01:00Z",
  "completed_at": null,
  "counts": {
    "files": 3,
    "parsed": 3,
    "parse_failed": 0,
    "low_quality": 1,
    "included": 1,
    "uncertain": 2,
    "excluded": 0
  }
}
```

Count rules:

- `parsed = contract_files where parse_status in (succeeded, low_quality)`.
- `parse_failed = contract_files where parse_status = failed`.
- `low_quality = contract_files where parse_status = low_quality`.
- Result counts are from `contract_screening_results`.
- `excluded` is always 0 in Phase 1.

This endpoint returns summaries for both `completed` and `failed` tasks.

### 11.3 `GET /api/screening-tasks/{task_id}/events`

Streams persisted events with fetch-based SSE. Native `EventSource` is not used because it cannot attach bearer auth headers.

Request headers:

- `Authorization: Bearer <token>` required.
- `Last-Event-ID: {task_id}:{sequence}` optional.

Behavior:

- Validate auth and task ownership before opening the stream.
- If `Last-Event-ID` is absent, malformed, from another task, or has a negative/non-integer sequence, send a synthetic `snapshot` event first and then replay persisted events from sequence 1.
- If `Last-Event-ID` is valid for this task, first check the terminal reconnect rule below; if it does not apply, replay persisted events with `sequence > last_sequence`.
- Terminal reconnect rule: if the task is completed or failed and `last_sequence` is at or beyond the latest persisted terminal event sequence, replay the latest persisted terminal `task_completed` or `task_failed` event once and close the stream without sending a snapshot or waiting for keepalives. Terminal replays are intentionally not filtered by `sequence > last_sequence` so reconnecting clients can observe a terminal event and treat stream closure as normal completion.
- Poll `stream_events` every 1 second.
- Send a keepalive comment every `SSE_KEEPALIVE_SECONDS`.
- Close after sending `task_completed` or `task_failed`.
- Detect client disconnect through the request disconnect API each poll iteration; stop polling and release resources when disconnected.
- Enforce a maximum non-terminal stream duration of 30 minutes; when exceeded, close the stream without mutating task state.

Response headers:

- `Content-Type: text/event-stream; charset=utf-8`.
- `Cache-Control: no-cache`.
- `Connection: keep-alive`.
- `X-Accel-Buffering: no`.

Wire format:

```text
id: {task_id}:{sequence}
event: {event_type}
data: {"event_id":"{task_id}:{sequence}","type":"progress","task_id":"{task_id}","timestamp":"2026-06-21T10:00:00Z","payload":{}}

```

The `type` value in the data object must equal `{event_type}` for the emitted event. The `progress` value above is only an example event type.

Synthetic snapshot uses sequence `0` in the wire ID:

```text
id: {task_id}:0
event: snapshot
data: {"event_id":"{task_id}:0","type":"snapshot","task_id":"{task_id}","timestamp":"2026-06-21T10:00:00Z","payload":{"status":"uploaded","progress_percent":5,"current_stage":"uploaded","counts":{"files":1,"parsed":0,"parse_failed":0,"low_quality":0,"included":0,"uncertain":0,"excluded":0}}}

```

### 11.4 `GET /api/screening-tasks/{task_id}/results`

Returns result buckets. Empty buckets are always present.

Success status: `200`.

Response:

```json
{
  "task_id": "7b6e8894-1d51-4b30-8a91-134d738aa51c",
  "buckets": {
    "included": [
      {
        "contract_id": "4efbf76d-2c83-4c8f-b1cf-65423d13fdb3",
        "file_name": "采购合同A.pdf",
        "download_url": "/api/contracts/4efbf76d-2c83-4c8f-b1cf-65423d13fdb3/download",
        "decision": "included",
        "reason": "keyword_evidence_matched",
        "matched_conditions": ["general_match"],
        "missing_conditions": [],
        "evidence": [
          {
            "page": 1,
            "text": "合同总价为人民币120万元",
            "source": "qmd",
            "score": 0.88,
            "condition_id": "general_match",
            "artifact_ref": "qmd://task-7b6e8894-1d51-4b30-8a91-134d738aa51c/4efbf76d-2c83-4c8f-b1cf-65423d13fdb3.md"
          }
        ],
        "confidence": 0.65,
        "parse_status": "succeeded",
        "file_size_bytes": 12345,
        "created_at": "2026-06-21T10:00:00Z",
        "updated_at": "2026-06-21T10:01:00Z"
      }
    ],
    "uncertain": [],
    "excluded": []
  }
}
```

Ordering:

- Sort bucket items by `confidence` descending, then `file_name` ascending.
- Evidence within a result is returned in classifier order: matched condition order from the plan, preserving each condition's capped evidence order. The results endpoint must not re-sort evidence globally by score.

This endpoint is valid for terminal `failed` tasks too. If all files fail parsing, it returns the persisted `uncertain` result for each failed file even though task status is `failed`.

For active non-terminal tasks, this endpoint returns `200` with currently persisted result rows bucketed by decision. If no results exist yet, all three buckets are empty arrays.

Before returning active-task results, perform the same authorized stale-task check used by summary/events reads. If the task is stale, mark it `failed/task_stale` first, then return buckets for the failed task.

For failed tasks with no persisted result rows, such as `enqueue_failed`, `artifact_write_failed`, `qmd_command_failed` before classification, or `task_stale`, this endpoint returns all three buckets as empty arrays. The failure reason is read from the task summary endpoint.

### 11.5 `GET /api/contracts/{contract_id}/download`

Returns the original uploaded file.

Behavior:

- Validate auth.
- Lookup contract.
- If contract is missing, return `404 not_found`.
- If owner mismatch, write `permission_denied` audit and return `404 not_found`.
- Resolve `stored_path`.
- Reject if resolved path is not under `STORAGE_ROOT`; return `404 not_found` and write `permission_denied` audit with `reason=path_escape`.
- If resolved file is missing, return `404 download_file_missing` and do not write `download` audit.
- If resolved file exists but is not readable as a regular file, return `404 download_file_unreadable` and do not write `download` audit.
- Write `download` audit before constructing and returning `FileResponse`.
- Return file with `Content-Disposition: attachment; filename*=UTF-8''<urlencoded original_filename>`.

Phase 1 does not create signed URLs. The frontend downloads through `fetch` with auth headers.

## 12. Upload Validation

Allowed extension/MIME pairs:

```text
.pdf  -> application/pdf
.png  -> image/png
.jpg  -> image/jpeg
.jpeg -> image/jpeg
```

Validation order per request:

1. Ensure file count is 1 to exactly `MAX_FILES_PER_TASK=5`. Zero `files` parts returns `400 file_empty`.
2. For each file, read to a temporary file while counting bytes and computing SHA-256.
3. Reject an upload part with empty filename and zero bytes as `file_empty`.
4. Reject an upload part with empty filename and non-zero bytes as `unsupported_file_type` because extension cannot be validated.
5. Reject empty file as `file_empty`.
6. Interpret `MAX_UPLOAD_MB` as a per-file binary MiB limit: `MAX_UPLOAD_MB * 1024 * 1024` bytes per uploaded file. Reject only when `file_size_bytes > limit_bytes`; a file exactly equal to the limit is accepted. There is no separate aggregate request-size limit in Phase 1 beyond `5 * MAX_UPLOAD_MB`.
7. Sanitize basename.
8. Validate extension/MIME pair. If the client MIME is missing or `application/octet-stream`, infer from extension only. If client MIME is present and mismatched, reject as `unsupported_file_type`.
9. For PDF, validate first bytes start with `%PDF` and then validate with `pypdf.PdfReader`; encrypted or unreadable PDF is `invalid_pdf`.
10. For PDF, reject page count greater than `MAX_PAGES_PER_FILE` as `too_many_pages`.
11. For image, validate with `Pillow.Image.verify`, reopen the image, and require `Image.format` to match the validated extension: `.png` -> `PNG`, `.jpg`/`.jpeg` -> `JPEG`. Unreadable image or format mismatch is `invalid_image`.
12. Reject image dimensions greater than `10000 x 10000` pixels or total pixels greater than `50_000_000` as `invalid_image`. Set `PIL.Image.MAX_IMAGE_PIXELS = 50_000_000` before validation and treat `DecompressionBombError` or `DecompressionBombWarning` as `invalid_image`.
13. Move temp file into final storage only after all files pass.

Persisted `content_type`:

- If the client MIME is one of the allowed MIME values and matches the extension, persist the client MIME.
- If the client MIME is missing or `application/octet-stream`, persist the inferred MIME from the extension.

Persisted `page_count`:

- PDF: persist the validated PDF page count.
- Image: persist `1`.
- Parser success later updates `contract_files.page_count` to `len(ParseResult.pages)`.
- `file_parsed.payload.page_count` always uses `len(ParseResult.pages)`.
- If `metadata.page_count` is positive and differs from `len(pages)`, mark the parse `low_quality`; do not persist `metadata.page_count` as `contract_files.page_count`.

Filename sanitization:

- Use basename only.
- Extension matching is case-insensitive. Persist and display the sanitized filename with a lowercase extension (`.pdf`, `.png`, `.jpg`, or `.jpeg`) regardless of original extension casing.
- Normalize whitespace to `_`.
- Replace characters outside `[A-Za-z0-9._\-\u4e00-\u9fff]` with `_`.
- Preserve extension when trimming to 180 characters including extension.
- If basename is empty after sanitization, use `contract` plus the original validated extension, for example `contract.pdf`.
- Final stored filename is `{contract_id}_{safe_filename}`.
- Duplicate display filenames in the same request append `_2`, `_3` before extension before final truncation.
- If duplicate suffix plus extension would exceed 180 characters, truncate the basename portion further and keep suffix plus extension intact.

All-or-nothing cleanup:

- If any validation or database insert fails, delete temp files and any already moved files for the request.
- Do not create a task row for validation failures.

## 13. Storage Layout

`STORAGE_ROOT` is an absolute path. Startup creates it if missing.

```text
{STORAGE_ROOT}/tasks/{task_id}/
  uploads/
    {contract_id}_{safe_filename}
  parsed/
    {contract_id}/
      contract.md
      metadata.json
      evidence.json
      pages/
        001.md
  qmd_docs/
    {contract_id}.md
```

Artifact rows:

- `contract.md` creates one `parsed_artifacts` row with `artifact_type=contract_markdown`, `page_number=0`.
- `metadata.json` creates one row with `artifact_type=metadata_json`, `page_number=0`.
- `evidence.json` creates one row with `artifact_type=evidence_json`, `page_number=0`.
- Each `pages/{page_number:03d}.md` file creates one row with `artifact_type=page_markdown`, `page_number` equal to that page.
- `qmd_docs/{contract_id}.md` does not create a `parsed_artifacts` row; it is a retrieval-side derived document referenced through `qmd://`.

Path rules:

- Database stores absolute paths for backend convenience.
- API responses never expose local paths.
- All read/write helpers resolve paths and assert they are under `STORAGE_ROOT`.
- `storage.ensure_storage_root()` creates only `STORAGE_ROOT` during startup.
- `storage.prepare_task_storage(task_id)` lazily creates `uploads/`, `parsed/`, and `qmd_docs/` for that task before upload finalization.
- Public `artifact_ref` values returned by APIs must be logical references only. They may be `qmd://...` or `artifact://tasks/{task_id}/contracts/{contract_id}/pages/{page_number}`. They must never be absolute or relative filesystem paths.
- Canonical public qmd reference format is `qmd://task-{full_task_uuid}/{full_contract_uuid}.md`. Shortened examples are illustrative only and must not be emitted by implementation.
- `qmd_docs/{contract_id}.md` starts with YAML front matter:

```markdown
---
contract_id: "4efbf76d-2c83-4c8f-b1cf-65423d13fdb3"
task_id: "7b6e8894-1d51-4b30-8a91-134d738aa51c"
file_name: "采购合同A.pdf"
---

# 采购合同A.pdf

<!-- page:1 -->
合同总价为人民币120万元
```

Front matter parsing is a constrained hand parser; do not add PyYAML in Phase 1. Only this exact form is supported:

- The document starts with a line containing only `---`.
- Front matter ends at the next line containing only `---`.
- Each metadata line is `key: "value"` with a double-quoted value and no escaped quotes.
- Recognized keys are exactly `contract_id`, `task_id`, and `file_name`.
- Unknown lines or malformed values make front matter invalid for mapping/sorting, but do not fail qmd search; invalid mapping falls through to unmapped handling.

## 14. Worker and State Machine

RQ job:

```python
def run_screening_task(task_id: str) -> None
```

Queue helper:

```python
def enqueue_screening_task(task_id: UUID) -> str:
    queue = Queue("screening", connection=redis_connection)
    job = queue.enqueue(
        "app.application.screening_runner.run_screening_task",
        str(task_id),
        job_timeout=1800,
        retry=None,
    )
    return job.id
```

If `queue.enqueue(...)` raises any exception, the API follows the `enqueue_failed` behavior in section 11.1.

Test behavior:

- Default backend pytest must not require a Redis service.
- Tests that exercise upload/API task creation monkeypatch `backend/app/application/task_queue.enqueue_screening_task` to return a deterministic fake job ID such as `test-job-{task_id}`.
- Tests that exercise `enqueue_failed` monkeypatch the same helper to raise an exception.
- Compose runtime uses the real RQ/Redis helper.

Queue:

- Name: `screening`.
- Timeout: 1800 seconds.
- Retry: disabled in Phase 1. The worker handles failures by marking the task `failed` and emitting `task_failed`. Automatic RQ retry is intentionally not used because task state is persisted after each failure.

Current stage values:

```text
uploaded
parsing
parsed
indexing
indexed
retrieving
classifying
completed
failed
```

`current_stage` always equals the current `TaskStatus` string in Phase 1.

State transitions:

```text
uploaded -> parsing -> parsed -> indexing -> indexed -> retrieving -> classifying -> completed
uploaded -> failed
parsing -> failed
parsing -> classifying -> failed  # all-files-parse-failed path only
parsed -> failed
indexing -> failed
indexed -> failed
retrieving -> failed
classifying -> failed
```

Progress percentages:

```text
uploaded: 5
parsing: 15 + floor(30 * parsed_or_failed_files / total_files), capped at 45
parsed: 50
indexing: 58
indexed: 65
retrieving: 72
classifying: 85 + floor(10 * classified_contracts / total_contracts), capped at 95
completed: 100
failed: keep last value
```

When `total_files` or `total_contracts` would be zero, use the lower bound for that stage.

Deterministic processing order:

- Parse files ordered by `contract_files.created_at`, then `original_filename`, then `id`.
- Run qmd queries in `ScreeningPlan.conditions` order and each condition's `qmd_queries` order.
- Emit `contract_classified` in the same order as the ordered `contract_files` list, including failed and low-quality contracts.

Partial parse behavior:

- Before calling the unified parsing service adapter for a file, set that contract `parse_status=running`, write `parse_started` audit, and emit `file_parsing`.
- After a valid `ParseResult`, evaluate low-quality rules, write all parser artifacts and qmd docs, and commit artifact rows before emitting `file_parsed`.
- If low-quality rules match and artifacts are durable, set `contract_files.parse_status=low_quality`, persist `parse_quality`, write `parse_succeeded` audit with `parse_status=low_quality`, and emit `file_parsed.payload.parse_status="low_quality"` in the same transaction.
- If low-quality rules do not match and artifacts are durable, set `contract_files.parse_status=succeeded`, persist `parse_quality`, write `parse_succeeded` audit with `parse_status=succeeded`, and emit `file_parsed.payload.parse_status="succeeded"` in the same transaction.
- File parse failure sets that contract `parse_status=failed`, writes `parse_failed` audit, and emits `file_parse_failed` in the same transaction.
- File parse failure does not immediately create a result. The later classification step creates the single `uncertain/parse_failed` result for that contract. This avoids violating the unique `(task_id, contract_id)` result constraint.
- Task continues if at least one file is `succeeded` or `low_quality`.
- If all files fail, build and persist `ScreeningPlan`, emit `criteria_parsed`, set task `status=classifying`, classify failed contracts as `uncertain/parse_failed`, emit `contract_classified` and classification `progress`, then set task `status=failed` with `error_code=parse_all_failed` and emit `task_failed`.
- `low_quality` files still write artifacts and qmd docs, but classifier always outputs `uncertain`.
- For every persisted `contract_screening_results` row, write `classification_completed` audit in the same transaction as the result insert and before emitting `contract_classified`.

Failure messages:

| Error code | Persisted `screening_tasks.error_message` | Stream `task_failed.payload.message` |
| --- | --- | --- |
| `parse_all_failed` | `All uploaded files failed parsing` | `All uploaded files failed parsing` |
| `task_stale` | `Task became stale and must be rerun` | `Task became stale and must be rerun` |
| `qmd_command_failed` | `qmd command failed` | `qmd command failed` |
| `artifact_write_failed` | `Unable to write parsed artifacts` | `Unable to write parsed artifacts` |
| `enqueue_failed` | `Unable to enqueue screening task` | `Unable to enqueue screening task` |
| `worker_unexpected_error` | `Unexpected worker error` | `Unexpected worker error` |

All task failures, including stale-task failures detected during summary/events reads, write a `task_failed` audit event with payload fields `task_id`, `stage`, `error_code`, and `message`.

`task_failed.payload.stage` values:

| Error code | Stage |
| --- | --- |
| `enqueue_failed` | `uploaded` |
| `parse_all_failed` | `classifying` |
| `artifact_write_failed` | `parsing` |
| `task_stale` | the task `current_stage` value before marking failed |
| `qmd_command_failed` during indexing | `indexing` |
| `qmd_command_failed` during retrieval/search | `retrieving` |
| `worker_unexpected_error` | the task `current_stage` value before marking failed |

Persist the same `stage` value in `task_failed` audit payload.

Unified parsing service failure messages:

| Error code | Stream `file_parse_failed.payload.error` | Audit `parse_failed.payload.message` |
| --- | --- | --- |
| `parse_service_rejected` | `Parsing service rejected the file` | `Parsing service rejected the file` |
| `parse_service_unavailable` | `Parsing service unavailable` | `Parsing service unavailable` |
| `parse_service_timeout` | `Parsing service request timed out` | `Parsing service request timed out` |
| `parse_service_invalid_response` | `Parsing service returned an invalid response` | `Parsing service returned an invalid response` |

Idempotency:

- At the start of `run_screening_task`, open a transaction and lock the `screening_tasks` row.
- If task status is `uploaded`, atomically claim it by setting `status=parsing`, `current_stage=parsing`, `progress_percent=15`, and `updated_at=now`, then commit before doing parse work.
- If task status is anything other than `uploaded`, including active, `completed`, or `failed`, return without work. This makes duplicate enqueue/manual invocation a no-op after the first worker claims the task.
- Emit `task_started` only after the successful `uploaded -> parsing` claim.
- There is no automatic retry path in Phase 1.
- A future manual retry endpoint must delete existing parsed artifacts, qmd candidate snippets, screening plan, and results for the task before restarting from `parsing`; this endpoint is out of scope.

Crash recovery:

- Phase 1 does not attempt resume/rebuild of active tasks after worker crash.
- If a task is left in `uploaded`, `parsing`, `parsed`, `indexing`, `indexed`, `retrieving`, or `classifying`, it is considered stuck. This covers API crashes after DB commit but before enqueue and lost Redis jobs.
- On the next authorized owner API read of task summary, events, or results, after auth and owner checks pass, if `updated_at` is older than 1800 seconds and status is active, mark the task `failed` with `error_code=task_stale`, `error_message="Task became stale and must be rerun"`, write `task_failed` audit, and emit `task_failed`.
- Stale mutation must be idempotent under concurrent task summary/events/results reads. Implement it in a helper that locks the `screening_tasks` row, rechecks that status is still active and stale, then updates the task and appends exactly one `task_failed` stream event and one `task_failed` audit event in the same transaction. If the recheck finds a terminal task or an existing `task_failed/task_stale` terminal event, return without emitting another terminal event.
- Cross-owner or invalid-token requests must return their auth error before stale mutation is considered.
- Stale tasks may have partial stream events and artifacts, but no automatic rerun is attempted.

## 15. Stream Events

Persist every business event in `stream_events`.

`snapshot` is synthetic and is never stored in `stream_events`. It uses wire sequence `0` only for SSE reconnect behavior.

`append_stream_event(session, task_id, event_type, payload)`:

- In PostgreSQL, lock the parent `screening_tasks` row with `SELECT ... FOR UPDATE`, then query current max sequence for that task and write sequence `max + 1`.
- In SQLite tests, use the single test session transaction and query current max sequence; tests run single-threaded.
- Commits in the same transaction as the related state update when possible.
- The SSE envelope `timestamp` is always `stream_events.created_at` for persisted events and current UTC time only for synthetic `snapshot`.

Event type union:

```text
snapshot
task_created
file_accepted
task_started
file_parsing
file_parsed
file_parse_failed
qmd_indexing
qmd_indexed
criteria_parsed
qmd_searching
qmd_retrieved
contract_classified
progress
task_completed
task_failed
```

Stored event types exclude `snapshot`; `snapshot` appears only in the TypeScript union and SSE response stream.

`stream_events.payload` stores only the inner payload object, not a wrapper containing `type` or `payload`.

Required golden-path event sequence for two files where both parse successfully:

1. `task_created`
2. `file_accepted` for each file
3. `task_started`
4. `progress` with status `parsing`
5. `file_parsing` for file 1
6. `file_parsed` for file 1
7. `progress`
8. `file_parsing` for file 2
9. `file_parsed` for file 2
10. `progress`
11. `qmd_indexing`
12. `qmd_indexed`
13. `progress` with status `indexed`
14. `criteria_parsed`
15. For each qmd query in deterministic query order, emit `qmd_searching` immediately followed by that same query's `qmd_retrieved` before starting the next query.
16. After all qmd query pairs complete, no additional qmd events are emitted.
17. `progress` with status `retrieving`
18. `contract_classified` for each contract
19. After each `contract_classified`, emit one classification `progress` event using the updated reviewed/result counts.
20. `task_completed`

Status commit order:

- Commit `status=parsing/current_stage=parsing` before `task_started`.
- After all file parse attempts complete, commit `status=parsed/current_stage=parsed` before starting qmd docs indexing.
- Commit `status=indexing/current_stage=indexing` in the same transaction as `qmd_indexing`.
- Commit `status=indexed/current_stage=indexed` in the same transaction as `qmd_indexed`.
- Build and persist `ScreeningPlan`, then emit `criteria_parsed` while status remains `indexed`.
- Commit `status=retrieving/current_stage=retrieving` before the first `qmd_searching`.
- Emit each `qmd_searching` before its qmd call and `qmd_retrieved` after candidates for that same query are persisted. Complete one query's search/retrieve pair before emitting the next query's `qmd_searching`.
- Commit `status=classifying/current_stage=classifying` after all qmd searches complete and before first `contract_classified`.
- Emit each `contract_classified` after that result row is persisted.
- Emit classification `progress` immediately after each `contract_classified` for both normal and all-files-failed paths.
- Commit `status=completed/current_stage=completed/progress_percent=100/completed_at=now` in the same transaction as `task_completed`.
- Any failure commits `status=failed/current_stage=failed/completed_at=now` in the same transaction as `task_failed`.

Progress event frequency:

- Emit `progress` exactly at the points listed in the golden-path sequence and all-files-failed sequence.
- Do not emit extra progress events solely because `status` changed to `parsed`, `indexing`, `retrieving`, or `completed`, unless that status is one of the listed progress points.
- `task_completed` carries completion counts; a separate `progress` event with `completed` status is not required and should not be asserted by tests.

For all-files-parse-failed:

1. Emit parse events and progress for each file.
2. Build and persist `ScreeningPlan`.
3. Keep task `status=parsing/current_stage=parsing` and `progress_percent` at the last parsing progress value while emitting `criteria_parsed`.
4. Set task status/current_stage to `classifying` after `criteria_parsed` and before the first `contract_classified`.
5. Run classification for failed contracts only, which persists one `uncertain/parse_failed` result for each file.
6. Emit `contract_classified` and classification `progress` for each failed contract.
7. Set task `failed`.
8. Emit `task_failed` with `error_code=parse_all_failed`.
9. Results endpoint remains available.

All-files-parse-failed tasks skip `parsed`, `indexing`, `indexed`, `retrieving`, `qmd_indexing`, `qmd_indexed`, `qmd_searching`, and `qmd_retrieved`. Classification progress starts at `85 + floor(10 * classified_contracts / total_contracts)`, using the same classifying formula as normal tasks; for one failed contract this emits `progress_percent=95` before `task_failed`.

Progress payload:

- Every `progress` event includes exactly `status`, `progress_percent`, `reviewed`, `included`, `uncertain`, and `excluded`.
- Before classification starts, `reviewed=0`, `included=0`, `uncertain=0`, and `excluded=0`.
- During classification, `reviewed` is the number of contracts with persisted results.
- `included`, `uncertain`, and `excluded` are current result counts.

Payload shapes below show API envelopes for readability; only the nested payload is persisted.

Stream and audit naming:

- Stream `file_parse_failed.payload.error` is the short user-facing error string consumed by the frontend.
- Audit `parse_failed.payload.message` is the audit message.
- Both use the same `error_code`.
- Supported `file_parse_failed.payload.error_code` values are only `parse_service_rejected`, `parse_service_unavailable`, `parse_service_timeout`, and `parse_service_invalid_response`.

Payload shapes:

```json
{"type":"task_created","payload":{"task_id":"uuid","title":"金额大于100万的合同","file_count":2}}
{"type":"file_accepted","payload":{"task_id":"uuid","contract_id":"uuid","file_name":"采购合同A.pdf","file_size_bytes":12345,"content_type":"application/pdf","sha256":"64-char-hex"}}
{"type":"task_started","payload":{"status":"parsing"}}
{"type":"file_parsing","payload":{"contract_id":"uuid","file_name":"采购合同A.pdf"}}
{"type":"file_parsed","payload":{"contract_id":"uuid","file_name":"采购合同A.pdf","parse_status":"succeeded","page_count":1,"quality":{"ocr_confidence":0.9,"warnings":[]}}}
{"type":"file_parse_failed","payload":{"contract_id":"uuid","file_name":"采购合同A.pdf","error_code":"parse_service_unavailable","error":"Parsing service unavailable"}}
{"type":"qmd_indexing","payload":{"collection_name":"task-7b6e8894-1d51-4b30-8a91-134d738aa51c","contract_count":2}}
{"type":"qmd_indexed","payload":{"collection_name":"task-7b6e8894-1d51-4b30-8a91-134d738aa51c","indexed_count":2}}
{"type":"criteria_parsed","payload":{"plan_id":"uuid","conditions":[{"id":"general_match","description":"金额大于100万的合同"}]}}
{"type":"qmd_searching","payload":{"query_text":"金额大于100万的合同","condition_id":"general_match"}}
{"type":"qmd_retrieved","payload":{"query_text":"金额大于100万的合同","condition_id":"general_match","candidate_count":2}}
{"type":"contract_classified","payload":{"contract_id":"uuid","file_name":"采购合同A.pdf","decision":"uncertain","reason":"structured_condition_requires_review"}}
{"type":"progress","payload":{"status":"classifying","progress_percent":90,"reviewed":1,"included":0,"uncertain":1,"excluded":0}}
{"type":"task_completed","payload":{"included_count":0,"uncertain_count":2,"excluded_count":0}}
{"type":"task_failed","payload":{"task_id":"uuid","stage":"retrieving","error_code":"qmd_command_failed","message":"qmd command failed"}}
```

Section 15 payload shapes are authoritative. The TypeScript `StreamEvent` union in section 22 must include every field shown here. Tests should assert required fields from these payload shapes for `task_created`, `file_accepted`, `file_parse_failed`, and `task_failed`.

Frontend type definitions must model this as a discriminated union on `type`.

## 16. Unified Parsing Service Adapter

Production parsing is provided by the enterprise unified parsing service. The Agent backend calls that service and normalizes its response. This project does not expose a production `/parse` service.

The adapter boundary is intentionally evidence-first: downstream code must depend on `ParseResult`, not on PaddleOCR, PaddleX, MinerU, or any specific provider response shape.

Interface:

```python
class ParsePage(BaseModel):
    page_number: int  # >= 1
    markdown: str

class ParseEvidence(BaseModel):
    page: int  # >= 1
    bbox: list[float] | None = None  # exactly 4 numbers when present
    text: str
    kind: Literal["text", "table", "title", "footer", "header"] = "text"
    confidence: float | None = None  # 0 <= confidence <= 1 when present

class ParseResult(BaseModel):
    parser_name: str
    parser_version: str
    provider_request_id: str | None = None
    quality: dict[str, Any]
    contract_markdown: str
    pages: list[ParsePage]
    evidence: list[ParseEvidence]
    metadata: dict[str, Any]

class UnifiedParsingServiceClient:
    def parse_file(self, contract_id: UUID, file_path: Path, filename: str) -> ParseResult: ...
```

HTTP request:

- Method: `POST`.
- URL: `PARSING_SERVICE_URL`.
- Multipart `file`: original file bytes and display filename.
- Multipart `contract_id`: UUID string.
- Header `X-API-Key: <PARSING_SERVICE_API_KEY>` only if configured.
- Timeout: 120 seconds.
- Retry once on timeout, non-timeout `httpx.TransportError`, or HTTP 5xx.
- Do not retry HTTP 4xx.

Required normalized response:

```json
{
  "parser_name": "enterprise-parser",
  "parser_version": "0.1",
  "provider_request_id": "parse-job-123",
  "quality": {"ocr_confidence": 0.9, "warnings": []},
  "contract_markdown": "甲方 A公司\n合同总价为人民币120万元",
  "pages": [
    {"page_number": 1, "markdown": "甲方 A公司\n合同总价为人民币120万元"}
  ],
  "evidence": [
    {
      "page": 1,
      "bbox": [0, 0, 100, 20],
      "text": "合同总价为人民币120万元",
      "kind": "text",
      "confidence": 0.9
    }
  ],
  "metadata": {"page_count": 1}
}
```

Provider-specific response handling:

- If the enterprise unified parsing service already returns this schema, the adapter validates it directly.
- If it returns an async job shape, the adapter owns submit/poll/download normalization and surfaces only the final `ParseResult` to the worker.
- If it returns provider-specific fields, the adapter maps them into `pages`, `contract_markdown`, `evidence`, `quality`, `metadata`, `parser_name`, `parser_version`, and `provider_request_id`.
- Provider raw response details may be stored under `metadata.provider_raw_summary`, but downstream code must not depend on provider-specific keys.

Validation:

- `contract_markdown` must be a string; empty string is allowed but makes low quality.
- `parser_name` and `parser_version` must be non-empty strings after trimming and at most 128 characters; invalid values raise `parse_service_invalid_response`.
- `pages` must be non-empty unless parse failed at HTTP level.
- `page_number` must be positive.
- Duplicate `pages[].page_number` values make the response invalid and raise `parse_service_invalid_response`; do not merge pages or let artifact writing hit the unique constraint.
- `metadata.page_count` must be positive when present.
- If `quality.ocr_confidence` is present, it must be numeric between 0 and 1; wrong type or out-of-range value raises `parse_service_invalid_response`.
- If `quality.warnings` is present, it must be a list of strings; wrong type raises `parse_service_invalid_response`.
- Missing `quality.ocr_confidence` does not invalidate the response and does not by itself make the parse low quality.
- Missing `quality.warnings` is treated as an empty list for low-quality rules.
- `bbox`, when present, must contain exactly four numeric values.
- `confidence`, when present, must be between 0 and 1.
- Evidence entries with non-positive page are dropped during normalization before constructing the final `ParseResult`; they do not invalidate the whole response.

Low quality if any condition is true:

- `quality.ocr_confidence < 0.65`.
- `contract_markdown.strip()` is empty.
- `metadata.page_count` is present and does not equal number of pages.
- `quality.warnings`, after the validation/defaulting rules above, contains `table_parse_failed` or `empty_text`.

Empty parser evidence alone does not make a parse low quality. This allows a clean parse with no qmd hits to classify as `no_evidence`.

Adapter failure mapping:

```python
class ParseServiceFailed(Exception):
    def __init__(self, error_code: str, message: str, retryable: bool = False) -> None: ...
    error_code: str
    message: str
    retryable: bool
```

- HTTP 4xx: raise `ParseServiceFailed(error_code="parse_service_rejected", message="Parsing service rejected the file", retryable=False)`.
- HTTP 5xx after retry: raise `ParseServiceFailed(error_code="parse_service_unavailable", message="Parsing service unavailable", retryable=True)`.
- Timeout after retry: raise `ParseServiceFailed(error_code="parse_service_timeout", message="Parsing service request timed out", retryable=True)`.
- Non-timeout transport failure after retry, including connection refused or DNS failure, raises `ParseServiceFailed(error_code="parse_service_unavailable", message="Parsing service unavailable", retryable=True)`.
- Invalid JSON or schema validation failure: raise `ParseServiceFailed(error_code="parse_service_invalid_response", message="Parsing service returned an invalid response", retryable=False)`.
- If a retry is attempted and the retry ends with a different terminal failure, emit the retry attempt's final `ParseServiceFailed.error_code` and message. The first attempt's retryable failure is not surfaced.
- Worker emits `file_parse_failed` with that error code and sets the contract `parse_status=failed`.

Fake parser service:

- `GET /healthz` returns `{"status":"ok"}` for Compose healthchecks.
- `POST /parse`.
- If filename contains `fail`, return HTTP 500.
- If filename contains `low`, return `ocr_confidence=0.5`, warning `empty_text`, and markdown `低质量扫描合同`.
- If filename contains `nohit`, return markdown `NOHIT 普通合同 无目标证据`, pages with same text, and empty evidence.
- If filename contains `long`, return the success response with markdown `甲方 A公司\n合同总价为人民币120万元，补充说明为LongEvidenceWrappingCheckLongEvidenceWrappingCheckLongEvidenceWrappingCheckLongEvidenceWrappingCheckLongEvidenceWrappingCheck` and matching page/evidence text. This fixture exists only to verify long evidence wrapping in the browser.
- Otherwise return the success response above.

Artifact writing and evidence assembly:

- `contract.md` is written from `contract_markdown`.
- `pages/{page_number:03d}.md` is written from each `pages[].markdown`.
- `metadata.json` is written from `metadata` plus `parser_name`, `parser_version`, `provider_request_id`, and `quality`.
- `evidence.json` is written from normalized evidence entries.
- `qmd_docs/{contract_id}.md` is written from non-empty `pages[].markdown` values joined in ascending page order with `<!-- page:N -->` markers.
- If all page Markdown values are blank after trimming, write `contract_markdown` as a fallback single page with `<!-- page:1 -->`.
- Blank individual page Markdown values are skipped when at least one other page has non-empty Markdown.
- This project may derive additional contract-screening evidence from qmd hits and parse pages, but it must not perform OCR, layout recognition, or document parsing model inference.

Artifact write failure:

- Write all artifacts for a contract into a temporary directory under `{STORAGE_ROOT}/tasks/{task_id}/parsed/{contract_id}.tmp`.
- Write the derived qmd doc first as `{STORAGE_ROOT}/tasks/{task_id}/parsed/{contract_id}.tmp/qmd_doc.md`.
- Move the temp directory atomically to `{STORAGE_ROOT}/tasks/{task_id}/parsed/{contract_id}` only after every artifact file and DB `parsed_artifacts` row is ready.
- After the parsed directory move succeeds, atomically move `parsed/{contract_id}/qmd_doc.md` to `qmd_docs/{contract_id}.md`.
- If the qmd doc move fails, delete `parsed/{contract_id}` and any partial `qmd_docs/{contract_id}.md`, roll back uncommitted artifact DB rows, and fail with `artifact_write_failed`.
- If any artifact or qmd doc write fails, delete the temp directory, set task `status=failed`, `error_code=artifact_write_failed`, `error_message="Unable to write parsed artifacts"`, write `task_failed` audit, emit `task_failed`, and stop the worker.
- If the final parsed directory and qmd doc moves succeed but the artifact DB commit fails, roll back the transaction, open a new transaction, lock the task, mark it `failed/artifact_write_failed`, write `task_failed` audit, emit `task_failed`, and leave the moved parsed/qmd files in place as audit-only residue. Do not attempt best-effort deletion after an ambiguous DB commit failure.
- Do not emit `file_parse_failed` for artifact write failure because parsing succeeded but persistence failed.
- Do not emit `file_parsed` for artifact write failure because artifacts are not durable.
- Leave the current contract `parse_status=running` when `artifact_write_failed` stops the task; task-level `failed/artifact_write_failed` is the source of truth.
- Do not create or update `contract_screening_results` after `artifact_write_failed`.

Worker catch-all failure handling:

- `run_screening_task` wraps post-claim work in a top-level `try/except Exception` after the initial idempotency claim.
- For any uncaught exception that is not already converted into a documented task failure, roll back the active transaction, open a new transaction, lock the `screening_tasks` row, and no-op if the task is already terminal.
- If the task is not terminal, capture `stage = task.current_stage`, set `status=failed`, `current_stage=failed`, keep the last `progress_percent`, set `error_code=worker_unexpected_error`, set `error_message="Unexpected worker error"`, set `completed_at=now`, write `task_failed` audit, and emit `task_failed` with payload `{task_id, stage, error_code: "worker_unexpected_error", message: "Unexpected worker error"}`.
- Do not expose exception text, stack traces, local paths, SQL statements, raw contract text, or bearer tokens in the task row, stream event, or audit payload.
- Re-raise is not required after the task is durably failed; Phase 1 RQ retry remains disabled.

## 17. qmd Adapter

qmd is called only through `backend/app/services/retrieval/qmd_client.py`.

Required Phase 1 app settings accept only `QMD_MODE=fixture`. `QMD_MODE=cli` and any unknown value are startup configuration errors in the shipped Phase 1 app; `QMD_MODE=cli` must fail Pydantic settings validation with message `qmd cli mode is not implemented in Phase 1`. Unsupported qmd modes never fail individual tasks at runtime because API and worker startup must reject them first.

Interface:

```python
class QmdIndexSummary(BaseModel):
    collection_name: str
    indexed_count: int
    qmd_docs_dir: str

class QmdResult(BaseModel):
    file: str
    docid: str | None = None
    score: float | None = None
    snippet: str | None = None
    text: str | None = None
    page_number: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

class QmdClient:
    def index_task(self, task_id: UUID, qmd_docs_dir: Path) -> QmdIndexSummary: ...
    def search(self, task_id: UUID, query_text: str, condition_id: str, top_k: int) -> list[QmdResult]: ...

def persist_qmd_results(
    session: Session,
    task: ScreeningTask,
    condition_id: str,
    query_text: str,
    qmd_docs_dir: Path,
    results: list[QmdResult],
) -> int: ...
```

Collection name:

```text
task-{task_id}
```

### 17.1 Fixture Mode

`QMD_MODE=fixture` is the default and the only mode required for the vertical-slice tests.

Index behavior:

- Verify `qmd_docs_dir` exists.
- Count `*.md` files.
- Return `indexed_count`.
- `qmd_indexing.payload.contract_count` counts only contracts with generated qmd docs, not all uploaded contracts.
- `qmd_indexed.payload.indexed_count` uses the same generated qmd doc count in fixture mode.

Search behavior:

- Read all `qmd_docs/*.md`.
- If a document contains `NOHIT`, that document returns no candidates.
- Remove YAML front matter from Markdown before token matching and snippet selection so metadata cannot create false matches.
- Normalize Latin characters in query and document body to lowercase before matching; Chinese remains unchanged.
- Build tokens in this order:
  1. Whitespace-separated query tokens with length >= 2 after lowercasing.
  2. Marker literals from section 18 whose lowercase form is a substring of the normalized query.
  3. Remove duplicate tokens while preserving first occurrence.
- Matching uses substring matching.
- A document matches if its normalized Markdown contains any token, or if the normalized query contains `金额` and the normalized document contains any amount marker from section 18.
- Return at most `top_k` results.
- Result `file` is `qmd://task-{task_id}/{contract_id}.md`.
- Result `docid` is `#{first 6 chars of sha256(markdown)}`.
- Result `score` is `0.88` for normal matches.
- Result `snippet` is selected by scanning Markdown lines in order after removing YAML front matter. Use the first line that contains the first matching token. If the special `金额` plus amount-marker rule matched and no token line was found, use the first line containing any amount marker. If no marker line is found, use the first 120 characters of the Markdown body.
- When multiple documents match, sort results by `file_name` from Markdown front matter ascending, then `contract_id` ascending, before applying `top_k`.

If a qmd item has both `snippet` and `text` missing or blank, the adapter drops that item and does not persist a `qmd_candidate_snippets` row for it.

Persistence mapping:

- `snippet_text`: `snippet.strip()` if present and non-blank, otherwise `text.strip()`.
- `artifact_ref`: normalized from `QmdResult.file`.
- `page_number`: `QmdResult.page_number` if positive, otherwise `null`; aggregation may fill page from qmd doc markers for evidence output, but the DB row remains unchanged.
- `raw_result`: full original qmd item before normalization.

Mode-independent qmd result mapping:

Mapping, `qmd_candidate_snippets` inserts, and `qmd_mapping_failed` audit writes happen in `persist_qmd_results(...)`, not in `aggregate_candidates(...)`. `aggregate_candidates(...)` is read-only over already persisted rows.

1. Parse `{task_id}` and `{contract_id}.md` from `QmdResult.file` when it is a canonical `qmd://task-{task_id}/{contract_id}.md` URI.
2. If `QmdResult.file` is a local path under the task's `qmd_docs_dir`, load that Markdown file and parse YAML front matter `task_id` and `contract_id`, but persist `artifact_ref` as canonical `qmd://task-{current_task_id}/{contract_id}.md` only after the mapping is valid.
3. Never attempt to load arbitrary paths outside `qmd_docs_dir`.
4. If the qmd URI format is invalid, treat the item as unmapped with reason `invalid_qmd_uri`.
5. If the local path is outside `qmd_docs_dir`, treat the item as unmapped with reason `disallowed_local_path`.
6. If required front matter exists but cannot be parsed by the constrained parser, treat the item as unmapped with reason `malformed_front_matter`.
7. If a qmd URI task id or front-matter `task_id` is present and differs from the current task id, treat the item as unmapped with reason `wrong_task`.
8. If the extracted or front-matter `contract_id` is not one of the current task's `contract_files`, treat the item as unmapped with reason `unknown_contract`.
9. If unmapped, save snippet with `contract_id=null`, `artifact_ref=null`, write `qmd_mapping_failed` audit with the reason selected above, and exclude it from classification.

`qmd_mapping_failed` audit payload:

- `artifact_ref`: canonical `qmd://...` when safely derivable; otherwise `null`. Never store a local path.
- `reason` values:
  - `invalid_qmd_uri`
  - `wrong_task`
  - `unknown_contract`
  - `malformed_front_matter`
  - `disallowed_local_path`

Candidate counts:

- `qmd_retrieved.payload.candidate_count` and audit `qmd_query.payload.candidate_count` are the number of persisted nonblank `qmd_candidate_snippets` rows for that query after qmd adapter normalization and blank-snippet dropping.
- These counts include unmapped rows and weak snippets; aggregation may later exclude them from classification.

Adapter raw result handling:

- Fixture and CLI adapters set `QmdResult.raw` to the original qmd item before normalization.
- If fixture test data omits `raw`, the fixture loader synthesizes it from the item object being loaded.
- If fixture mode constructs a result directly from a Markdown document match rather than JSON fixture data, set `raw` to `{ "file": file, "docid": docid, "score": score, "snippet": snippet }`.
- `raw_result` persistence uses `QmdResult.raw`; it is never `null`.

### 17.2 CLI Mode

`QMD_MODE=cli` is a future adapter contract, not an accepted runtime mode in the shipped Phase 1 app. Current development verification uses `QMD_MODE=fixture`.

Implementation requirement:

- Shipped Phase 1 implements only `QMD_MODE=fixture`.
- Shipped Phase 1 settings reject `QMD_MODE=cli` with startup validation message `qmd cli mode is not implemented in Phase 1`.
- The CLI contract below is documentation for a later adapter and for local reference tests; it is not part of the required Phase 1 app or test gate.

Runtime provisioning:

- Optional Docker Compose usage does not install qmd and must keep `QMD_MODE=fixture`.
- Because shipped Phase 1 rejects `QMD_MODE=cli` during settings validation, the CLI wrapper is not reachable from API or worker runtime.
- If a later branch enables the CLI wrapper, it must require `QMD_BIN` to point to an installed qmd executable; missing or non-executable `QMD_BIN` must raise `QmdCommandFailed` and fail the task with `qmd_command_failed`.
- README must describe CLI mode as a future/reference adapter contract, externally provisioned, and excluded from the default verification gate.

The CLI contract is based on `github.com/tobi/qmd` / npm package `@tobilu/qmd` README behavior current to this design date. The wrapper must use BM25 `search`, not hybrid `query`, because Phase 1 should not require local LLM reranking. If qmd changes this CLI contract, fixture mode remains the supported Phase 1 path and the CLI contract tests should be updated separately.

Commands:

```sh
qmd --index "$QMD_INDEX_NAME" collection add "$qmd_docs_dir" --name "task-$task_id"
qmd --index "$QMD_INDEX_NAME" search --json -n "$top_k" -c "task-$task_id" "$query"
```

`$top_k` is the `top_k` argument passed to `QmdClient.search(...)`. Callers pass `settings.QMD_TOP_K` by default.

Execution safety:

- Use `subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=120)`.
- Build argv as a list; never concatenate `query` into a shell string.
- `collection add` argv: `[settings.QMD_BIN, "--index", settings.QMD_INDEX_NAME, "collection", "add", str(qmd_docs_dir), "--name", collection_name]`.
- `search` argv: `[settings.QMD_BIN, "--index", settings.QMD_INDEX_NAME, "search", "--json", "-n", str(top_k), "-c", collection_name, query_text]`.
- On timeout, non-zero exit, or JSON parse failure, raise `QmdCommandFailed`.
- Persist sanitized stderr under `screening_tasks.metrics["qmd_stderr"]`: first 500 characters with control characters removed. Do not persist query text in `error_message` beyond audit `qmd_query`.

If later semantic search is enabled, embedding can be added with:

```sh
qmd --index "$QMD_INDEX_NAME" embed -c "task-$task_id"
```

Do not call `embed` in Phase 1 by default.

Expected CLI JSON item, accepting either array output or newline-delimited JSON:

```json
{
  "file": "qmd://task-7b6e8894-1d51-4b30-8a91-134d738aa51c/4efbf76d-2c83-4c8f-b1cf-65423d13fdb3.md",
  "docid": "#abc123",
  "score": 0.82,
  "snippet": "合同总价为人民币120万元"
}
```

Failure:

```python
class QmdCommandFailed(Exception):
    def __init__(self, message: str, stderr: str | None = None) -> None: ...
    message: str
    stderr: str | None
```

- Non-zero qmd exit or invalid JSON raises `QmdCommandFailed`.
- Worker sets task `failed`, `error_code=qmd_command_failed`, emits `task_failed`.

## 18. ScreeningPlan

`build_screening_plan(raw_query: str) -> ScreeningPlanPayload`.

Phase 1 creates a single condition named `general_match`.

Plan JSON:

```json
{
  "target": "contract_file",
  "conditions": [
    {
      "id": "general_match",
      "description": "金额大于100万的合同",
      "operator": "semantic_match",
      "value": "金额大于100万的合同",
      "qmd_queries": ["金额大于100万的合同", "金额 总价 价款 人民币"],
      "evidence_required": 1,
      "structured": true
    }
  ],
  "decision_policy": "phase1_keyword_candidate_uncertain_on_structured_comparison"
}
```

Rules:

- Trim the raw query.
- First qmd query is the full raw query.
- Add expansion queries for every matched marker group in fixed group order: amount, party, renewal, payment, date.
- Remove duplicate queries while preserving order.
- `operator` is always `semantic_match`.
- `evidence_required` is always `1`.
- `structured=true` if any structured comparison marker appears.
- Marker matching is substring-based. Latin marker matching is case-insensitive; Chinese marker matching is direct substring matching.

Marker groups:

```text
amount: 金额, 总价, 价款, 万元, 人民币, RMB, 含税
party: 供应商, 甲方, 乙方, 客户, 公司
renewal: 续约, 自动续约, 顺延, 续期
payment: 付款, 支付, 账期
date: 签署, 生效, 到期, 年后, 以后, 之前
```

When qmd fixture mode says “marker literals from section 18,” it means only the marker-group terms listed above. If a term appears in both marker groups and structured comparison markers, such as `年后`, `以后`, or `之前`, it still counts as a marker-group literal for qmd fixture matching and expansion. Structured-only comparison markers that are not in marker groups are excluded from qmd fixture marker literals.

Structured comparison markers:

```text
大于, 超过, 小于, 少于, 不少于, 不超过, 以上, 以下, 年后, 以后, 之前, 早于, 晚于
```

Marker expansion queries:

- If amount group matches, add `金额 总价 价款 人民币`.
- If party group matches, add `甲方 乙方 供应商 公司`.
- If renewal group matches, add `自动续约 续约 顺延 续期`.
- If payment group matches, add `付款 支付 账期`.
- If date group matches, add `签署 生效 到期 日期`.

## 19. Aggregation and Evidence

`aggregate_candidates(task_id, qmd_docs_dir, contract_files, qmd_snippets) -> dict[UUID, ContractCandidate]`.

Input:

- `task_id`: UUID for logical qmd reference normalization.
- `qmd_docs_dir`: path to `{STORAGE_ROOT}/tasks/{task_id}/qmd_docs`.
- `contract_files`: list of `ContractFile` ORM instances for the task.
- `qmd_snippets`: list of `QmdCandidateSnippet` ORM instances for the task. Rows with `contract_id is None` are accepted as input but dropped before grouping.

Output per contract:

```python
class ContractCandidate(BaseModel):
    contract_id: UUID
    file_name: str
    parse_status: ParseStatus
    parse_quality: dict[str, Any]
    file_size_bytes: int
    snippets_by_condition: dict[str, list[EvidenceItem]]
```

Aggregation must return one `ContractCandidate` for every `ContractFile` in the task, including failed-parse and no-hit contracts. Contracts with no mapped non-weak qmd snippets have empty `snippets_by_condition`.

Evidence item JSON:

```json
{
  "page": 1,
  "text": "合同总价为人民币120万元",
  "source": "qmd",
  "score": 0.88,
  "condition_id": "general_match",
  "artifact_ref": "qmd://task-7b6e8894-1d51-4b30-8a91-134d738aa51c/4efbf76d-2c83-4c8f-b1cf-65423d13fdb3.md"
}
```

Evidence `artifact_ref` normalization:

- `qmd_candidate_snippets.artifact_ref` is already normalized before DB insert and must be either canonical `qmd://task-{task_id}/{contract_id}.md` or `null`.
- Aggregation keeps canonical `qmd://` refs and sets any non-canonical value to `null`.
- Local qmd paths may appear only inside `qmd_candidate_snippets.raw_result`, never in the `artifact_ref` column or API evidence.

Page extraction:

- If qmd result has `page_number`, use it.
- Else parse `<!-- page:N -->` markers preceding the snippet in qmd doc.
- Else use `null`.

Weak snippet:

- `snippet_text.strip()` length < 8.
- Or `score` exists and is `< 0.2`.

Weak snippets are filtered out before `ContractCandidate.snippets_by_condition`; they are not returned in API evidence arrays and do not count for matching. They may remain in `qmd_candidate_snippets` for debugging.

Deduplication and limits:

- Before grouping, deduplicate non-weak snippets per `(contract_id, condition_id, artifact_ref, page, normalized_text)`.
- `normalized_text` is `snippet_text.strip()` with internal whitespace collapsed to a single space.
- If duplicates have different scores, keep the row with the highest non-null score; if tied, keep the earliest `created_at`.
- For each `(contract_id, condition_id)`, keep at most 5 evidence items sorted by `score` descending with null scores last, then `text` ascending.

## 20. Classification

`classify_contract(candidate, plan) -> ContractScreeningDecision`.

Return model:

```python
class ContractScreeningDecision(BaseModel):
    contract_id: UUID
    decision: ResultDecision
    reason: str
    matched_conditions: list[str]
    missing_conditions: list[str]
    evidence: list[EvidenceItem]
    confidence: float
```

Reason codes:

```text
parse_failed
low_quality_parse
structured_condition_requires_review
no_evidence
keyword_evidence_matched
```

Rules, in order:

1. Build `condition_evidence` from `candidate.snippets_by_condition`; aggregation has already removed weak snippets and capped each condition at 5 items.
2. `matched_conditions` are condition IDs whose evidence count is at least `condition.evidence_required`.
3. `missing_conditions` are all other condition IDs, in plan order.
4. Output `evidence` is the concatenation of evidence items for `matched_conditions` in plan condition order, preserving each condition's evidence order and capped at 10 total items.
5. If `parse_status=failed`, decision `uncertain`, reason `parse_failed`, confidence `0.0`, `matched_conditions=[]`, `missing_conditions` equal all plan condition IDs, and `evidence=[]`.
6. If `parse_status=low_quality`, decision `uncertain`, reason `low_quality_parse`, confidence `0.2`, and use the computed `matched_conditions`, `missing_conditions`, and `evidence`.
7. If no condition has enough evidence, decision `uncertain`, reason `no_evidence`, confidence `0.1`, `matched_conditions=[]`, `missing_conditions` equal all plan condition IDs, and `evidence=[]`.
8. If any matched condition has `structured=true`, decision `uncertain`, reason `structured_condition_requires_review`, confidence `0.45`, and use the computed `matched_conditions`, `missing_conditions`, and `evidence`.
9. If every condition has at least `evidence_required` evidence, decision `included`, reason `keyword_evidence_matched`, confidence `0.65`, and use the computed `matched_conditions`, `missing_conditions=[]`, and `evidence`.
10. Otherwise decision `uncertain`, reason `no_evidence`, confidence `0.1`, and use `matched_conditions=[]`, `missing_conditions` equal all plan condition IDs, and `evidence=[]`.

`matched_conditions`:

- Condition IDs with enough non-weak evidence, except forced-empty outcomes described above.

`missing_conditions`:

- Condition IDs without enough non-weak evidence, except forced-all outcomes described above.

`excluded` is never emitted by this function in Phase 1.

## 21. Frontend UX

Routes:

```text
/                UploadPage
/tasks/:taskId   TaskProgressPage
```

### 21.1 Token Handling

- Token is stored in `localStorage.contract_search_token`.
- If missing, UploadPage shows a token input.
- If missing on direct navigation to `/tasks/:taskId`, TaskProgressPage shows the same token input above the task content area and does not call APIs until a token is saved.
- Default placeholder is `dev-token`.
- Token input has a `保存 Token` button. Clicking it trims the input, saves non-empty value through `saveToken`, clears token-related error text, and lets the page continue with API calls.
- Typing in the token input alone does not save. Upload submit does not implicitly save the token; the token must be saved first.
- "Clear token" button removes the token and returns to token input.
- Any API `401` clears the token and displays `Token 无效，请重新输入`.
- On any `401`, abort active SSE fetch through `AbortController`, clear polling intervals, cancel queued result fetches by ignoring their resolution, clear token, and render the token input.
- Frontend never stores owner ID.

### 21.2 UploadPage

Controls:

- Token input when token missing.
- Query textarea.
- File input with `multiple` and `accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"`.
- Submit button disabled when token missing, query empty, no files, more than 5 files, or upload in progress.

On submit:

- POST multipart to `/api/screening-tasks`.
- Navigate to `/tasks/{task_id}` on success.
- Render API error message on failure.

### 21.3 TaskProgressPage

On mount:

1. If no token is present, render token input and do not call APIs.
2. Fetch task summary.
3. Start fetch-based SSE using stored token.
4. Fetch results after `task_completed` or `task_failed`; also fetch results immediately if summary status is `completed` or `failed`.
5. Track the latest SSE `event_id` in component state for display/debug only.
6. If SSE fails before a terminal event, abort the SSE subscription and switch to polling summary every 2 seconds; Phase 1 does not attempt automatic SSE reconnect from `lastEventId`.
7. Fetch results when polled status is `completed` or `failed`.

Error rendering:

- Initial summary `404 not_found` renders `任务不存在或无权访问`.
- Initial summary `401` follows the token-clearing behavior in section 21.1.
- Initial summary `500 internal_error`, network errors, or non-JSON failures render `任务加载失败，请稍后重试`.
- These non-401 failures stop SSE/polling startup and keep the token unchanged.

Display:

- Title and status.
- If latest task summary has `status=failed`, render a failure banner above the progress bar with `data-testid="task-failure-banner"`, text `任务失败：{error_message || error_code || "未知错误"}`, and the safe backend `error_code` when present.
- The failure banner is rendered for both SSE terminal failure and polling fallback failure because `TaskProgressPage` refreshes summary before or while fetching final results.
- Latest SSE event id renders as `最新事件: {event_id}` with `data-testid="latest-event-id"`.
- Progress bar using `progress_percent`.
- Timeline of received events.
- Result buckets visible even before completion, initially empty.
- Layout uses a single responsive page column with max content width 1120px on desktop and 16px page padding on mobile.
- On desktop, task status/progress appears above a two-column area: timeline on the left and result buckets on the right.
- On mobile, timeline and result buckets stack vertically.
- Long file names, reason codes, and evidence snippets wrap; no horizontal scrolling is allowed at 390px viewport width.

### 21.4 Components

`ProgressTimeline`:

- Props: `{ events: StreamEvent[]; currentStage: string; progressPercent: number }`.
- Renders current stage text.
- Each event row has `data-testid="event-{type}"`.

`ResultBuckets`:

- Props: `{ buckets: ResultBucketsPayload; onDownload(contractId: string, downloadUrl: string, fileName: string): void; onOpenEvidence(item: ContractResultItem, trigger: HTMLElement): void }`.
- Evidence drawer state is owned by `TaskProgressPage`; `ResultBuckets` passes `onOpenEvidence` through to each `ContractResultCard`.
- Renders headings exactly:
  - `入选合同`
  - `待复核合同`
  - `已排除合同`

`ContractResultCard`:

- Props: `{ item: ContractResultItem; onDownload(contractId: string, downloadUrl: string, fileName: string): void; onOpenEvidence(item: ContractResultItem, trigger: HTMLElement): void }`.
- Renders file name.
- Renders decision labels:
  - `included` -> `入选`
  - `uncertain` -> `待复核`
  - `excluded` -> `已排除`
- Renders reason code.
- Has "证据" button when evidence is non-empty.
- Has download button using text icon `↓` with `aria-hidden="true"` plus text `下载`; no icon library is required in Phase 1.

`EvidenceDrawer`:

- Props: `{ item: ContractResultItem | null; open: boolean; returnFocusTo: HTMLElement | null; onClose(): void }`.
- Uses `role="dialog"`, `aria-modal="true"`, and `aria-labelledby="evidence-drawer-title"`.
- Renders a visible title element with id `evidence-drawer-title` and text `证据详情`.
- Opens from a result card.
- Renders page number, snippet text, score, and condition ID.
- When opened, stores the previously focused evidence button in `returnFocusTo` and moves focus to the close button.
- Pressing `Escape` closes the drawer.
- `Tab` and `Shift+Tab` cycle focus within drawer focusable controls while open; Phase 1 drawer focusable controls are the close button and any evidence-action buttons rendered inside the drawer.
- Close button returns focus to the originating evidence button.

### 21.5 Download

Frontend download function:

```ts
async function downloadContract(token: string, downloadUrl: string, fileName: string): Promise<void>
```

Behavior:

- `fetch(apiBase + downloadUrl, { headers: { Authorization: `Bearer ${token}` } })`.
- If response is not OK, throw `ApiError`; do not clear token inside this function.
- Convert body to blob.
- Create object URL.
- Click temporary anchor with `download=fileName`.
- Revoke object URL.

Direct navigation to `download_url` is not used.

### 21.6 Frontend API Libraries

`frontend/src/lib/api.ts` exports:

```ts
export class ApiError extends Error {
  constructor(status: number, code: string, message: string, details?: Record<string, unknown>);
  status: number;
  code: string;
  details: Record<string, unknown>;
}

export function getToken(): string | null;
export function saveToken(token: string): void;
export function clearToken(): void;
export async function createScreeningTask(input: { token: string; query: string; title?: string; files: File[] }): Promise<CreateTaskResponse>;
export async function getTaskSummary(token: string, taskId: string): Promise<TaskSummaryResponse>;
export async function getTaskResults(token: string, taskId: string): Promise<TaskResultsResponse>;
export async function downloadContract(token: string, downloadUrl: string, fileName: string): Promise<void>;
```

All API functions use `apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"`.

API functions, including `downloadContract`, throw `ApiError` for non-2xx responses. If the response body matches the backend error envelope, use its `code`, `message`, and `details`; otherwise use `code="network_error"` and message `网络连接失败` for fetch failures, and `code="http_error"` and message `请求失败，请稍后重试` for unexpected non-JSON HTTP errors. For fetch/network failures with no HTTP response, `ApiError.status` must be `0`. API functions never mutate token storage directly.

`downloadContract` receives token explicitly. The caller handles errors: on `ApiError.status === 401`, caller invokes `clearToken()` and updates UI to `Token 无效，请重新输入`; other errors render the error message near the download button.

`frontend/src/lib/sse.ts` exports:

```ts
export interface SseSubscription {
  abort(): void;
}

export function subscribeTaskEvents(input: {
  token: string;
  taskId: string;
  lastEventId?: string;
  onEvent(event: StreamEvent): void;
  onError(error: ApiError | Error): void;
  onComplete(): void;
}): SseSubscription;
```

`subscribeTaskEvents` uses `fetch` with `Authorization` and an `AbortController`, parses SSE frames incrementally, tracks the latest event id internally, calls `onEvent` for every parsed event including terminal events, and calls `onComplete` after `onEvent` for `task_completed` or `task_failed`.

If the response body ends cleanly before a terminal event is received, call `onError(new Error("sse_stream_ended"))`; TaskProgressPage treats this like any other pre-terminal SSE failure and switches to polling.

SSE client parsing rules:

- If `lastEventId` is provided, send request header `Last-Event-ID: <lastEventId>`.
- Decode streamed `Uint8Array` chunks with `TextDecoder` in streaming mode and preserve partial lines between chunks.
- Accept both LF and CRLF line endings.
- Ignore comment lines beginning with `:`, including keepalive comments.
- Join multiple `data:` lines in one event with `\n` before JSON parsing.
- Dispatch an event only when a blank line terminates an SSE frame.
- Use the frame `id:` as `event.event_id` if present; otherwise use the JSON payload `event_id`.

For non-2xx SSE responses, `subscribeTaskEvents` parses the backend error envelope into `ApiError` using the same rules as `api.ts`, then calls `onError`.

Calling `SseSubscription.abort()` is caller-initiated cancellation. It must abort the fetch and must not call `onError` or `onComplete`.

## 22. TypeScript API Types

`frontend/src/lib/types.ts` defines:

```ts
export type TaskStatus =
  | 'uploaded' | 'parsing' | 'parsed' | 'indexing' | 'indexed'
  | 'retrieving' | 'classifying' | 'completed' | 'failed';

export type ResultDecision = 'included' | 'uncertain' | 'excluded';
export type StreamParseStatus = 'succeeded' | 'low_quality';
export type FileParseErrorCode =
  | 'parse_service_rejected'
  | 'parse_service_unavailable'
  | 'parse_service_timeout'
  | 'parse_service_invalid_response';

export interface TaskCounts {
  files: number;
  parsed: number;
  parse_failed: number;
  low_quality: number;
  included: number;
  uncertain: number;
  excluded: number;
}

export interface CreateTaskResponse {
  task_id: string;
  title: string;
  raw_query: string;
  status: TaskStatus;
  progress_percent: number;
  events_url: string;
  results_url: string;
}

export interface TaskSummaryResponse {
  task_id: string;
  title: string;
  raw_query: string;
  status: TaskStatus;
  progress_percent: number;
  current_stage: string;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  counts: TaskCounts;
}

export interface EvidenceItem {
  page: number | null;
  text: string;
  source: 'qmd';
  score: number | null;
  condition_id: string;
  artifact_ref: string | null;
}

export interface ContractResultItem {
  contract_id: string;
  file_name: string;
  download_url: string;
  decision: ResultDecision;
  reason: string;
  matched_conditions: string[];
  missing_conditions: string[];
  evidence: EvidenceItem[];
  confidence: number;
  parse_status: 'pending' | 'running' | 'succeeded' | 'low_quality' | 'failed';
  file_size_bytes: number;
  created_at: string;
  updated_at: string;
}

export interface ResultBucketsPayload {
  included: ContractResultItem[];
  uncertain: ContractResultItem[];
  excluded: ContractResultItem[];
}

export interface TaskResultsResponse {
  task_id: string;
  buckets: ResultBucketsPayload;
}

export type StreamEvent =
  | { type: 'snapshot'; event_id: string; task_id: string; timestamp: string; payload: { status: TaskStatus; progress_percent: number; current_stage: string; counts: TaskCounts } }
  | { type: 'task_created'; event_id: string; task_id: string; timestamp: string; payload: { task_id: string; title: string; file_count: number } }
  | { type: 'file_accepted'; event_id: string; task_id: string; timestamp: string; payload: { task_id: string; contract_id: string; file_name: string; file_size_bytes: number; content_type: string; sha256: string } }
  | { type: 'task_started'; event_id: string; task_id: string; timestamp: string; payload: { status: TaskStatus } }
  | { type: 'file_parsing'; event_id: string; task_id: string; timestamp: string; payload: { contract_id: string; file_name: string } }
  | { type: 'file_parsed'; event_id: string; task_id: string; timestamp: string; payload: { contract_id: string; file_name: string; parse_status: StreamParseStatus; page_count: number | null; quality: Record<string, unknown> } }
  | { type: 'file_parse_failed'; event_id: string; task_id: string; timestamp: string; payload: { contract_id: string; file_name: string; error_code: FileParseErrorCode; error: string } }
  | { type: 'qmd_indexing'; event_id: string; task_id: string; timestamp: string; payload: { collection_name: string; contract_count: number } }
  | { type: 'qmd_indexed'; event_id: string; task_id: string; timestamp: string; payload: { collection_name: string; indexed_count: number } }
  | { type: 'criteria_parsed'; event_id: string; task_id: string; timestamp: string; payload: { plan_id: string; conditions: Array<{ id: string; description: string }> } }
  | { type: 'qmd_searching'; event_id: string; task_id: string; timestamp: string; payload: { query_text: string; condition_id: string } }
  | { type: 'qmd_retrieved'; event_id: string; task_id: string; timestamp: string; payload: { query_text: string; condition_id: string; candidate_count: number } }
  | { type: 'contract_classified'; event_id: string; task_id: string; timestamp: string; payload: { contract_id: string; file_name: string; decision: ResultDecision; reason: string } }
  | { type: 'progress'; event_id: string; task_id: string; timestamp: string; payload: { status: TaskStatus; progress_percent: number; reviewed: number; included: number; uncertain: number; excluded: number } }
  | { type: 'task_completed'; event_id: string; task_id: string; timestamp: string; payload: { included_count: number; uncertain_count: number; excluded_count: number } }
  | { type: 'task_failed'; event_id: string; task_id: string; timestamp: string; payload: { task_id: string; stage: string; error_code: string; message: string } };
```

## 23. Docker Compose

Services:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: contract
      POSTGRES_PASSWORD: contract
      POSTGRES_DB: contracts
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U contract -d contracts"]
      interval: 5s
      timeout: 5s
      retries: 20

  redis:
    image: redis:7
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 20

  api:
    build: ./backend
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - contract_storage:/data/storage
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  worker:
    build: ./backend
    command: sh -c "rq worker screening --url \"$$REDIS_URL\""
    env_file:
      - .env
    volumes:
      - contract_storage:/data/storage
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  frontend:
    build: ./frontend
    command: npm run dev -- --host 0.0.0.0
    ports:
      - "5173:5173"
    environment:
      VITE_API_BASE_URL: http://localhost:8000

volumes:
  postgres_data:
  contract_storage:
```

Backend Dockerfile:

- Base `python:3.12-slim`.
- Install backend package with test/dev dependencies not required in runtime image.
- Workdir `/app`.
- Expose 8000.

Frontend Dockerfile:

- Base `node:22-slim`.
- Workdir `/app`.
- Copy `package.json` and `package-lock.json`, run `npm ci`, copy source.
- Expose 5173.

Production parsing service:

- Not built by this repository.
- The backend calls the enterprise unified parsing service configured by `PARSING_SERVICE_URL`.
- Optional Compose usage requires an enterprise or custom parser URL. Current development verification uses local Python and Node commands only.

## 24. Test Fixtures

Backend fixture files:

`parse_success.json`:

```json
{
  "parser_name": "stub-parser",
  "parser_version": "0.1",
  "quality": {"ocr_confidence": 0.9, "warnings": []},
  "contract_markdown": "甲方 A公司\n合同总价为人民币120万元",
  "pages": [{"page_number": 1, "markdown": "甲方 A公司\n合同总价为人民币120万元"}],
  "evidence": [{"page": 1, "bbox": [0, 0, 100, 20], "text": "合同总价为人民币120万元", "kind": "text", "confidence": 0.9}],
  "metadata": {"page_count": 1}
}
```

`parse_low_quality.json`:

```json
{
  "parser_name": "stub-parser",
  "parser_version": "0.1",
  "quality": {"ocr_confidence": 0.5, "warnings": ["empty_text"]},
  "contract_markdown": "低质量扫描合同",
  "pages": [{"page_number": 1, "markdown": "低质量扫描合同"}],
  "evidence": [],
  "metadata": {"page_count": 1}
}
```

`parse_nohit.json`:

```json
{
  "parser_name": "stub-parser",
  "parser_version": "0.1",
  "quality": {"ocr_confidence": 0.9, "warnings": []},
  "contract_markdown": "NOHIT 普通合同 无目标证据",
  "pages": [{"page_number": 1, "markdown": "NOHIT 普通合同 无目标证据"}],
  "evidence": [],
  "metadata": {"page_count": 1}
}
```

`qmd_results.json`:

```json
[
  {
    "file": "qmd://task-{{task_id}}/{{contract_id}}.md",
    "docid": "#abc123",
    "score": 0.88,
    "snippet": "合同总价为人民币120万元"
  }
]
```

Tests replacing `{{task_id}}` and `{{contract_id}}` must use full UUID strings. Literal placeholders must not reach adapter parsing.

Backend tests may generate valid one-page PDFs in memory using a helper, or use image fixtures generated with Pillow. Do not commit large binary fixtures.

Manual sample generator:

- `scripts/create_manual_samples.py` creates `samples/purchase.png`, `samples/nohit.png`, `samples/low.png`, and `samples/very-long-contract-file-name-for-responsive-wrapping-check-abcdefghijklmnopqrstuvwxyz-0123456789.png`.
- It uses only Python standard library by writing a base64-decoded 1x1 PNG fixture to each filename; no Pillow dependency is required.
- These files are ignored by git through `.gitignore`.
- The fake parser service keys off filename, so `nohit.png` triggers the no-hit fixture, `low.png` triggers low quality, and the long filename sample triggers the long-evidence fixture.

## 25. Verification Criteria

Current development-stage verification does not use Docker or Docker Compose as a test gate. Required checks are local process-level commands only.

```sh
cd backend
../.venv/bin/pytest
```

```sh
cd frontend
npm test -- --run
npm run build
```

Default backend tests must pass without a running PostgreSQL, Redis, Docker, or Compose service. Frontend tests must run against mocked browser/network primitives and must not require a live dev server.

Chunked upload validation:

- Phase 1 performance claims are application-level only. FastAPI/Starlette may spool multipart upload bodies before route code receives `UploadFile`; this design does not guarantee zero-copy or bounded ASGI parser memory.
- Backend validation code must read each `UploadFile.file` in chunks of at most 1 MiB and stream accepted bytes to a temporary file while calculating size and SHA-256. It must not call `await file.read()` without a size argument, accumulate all chunks into a list, or build one large `bytes` object for the full upload.
- `MAX_UPLOAD_MB=50` is a validation limit, not a proven per-process memory ceiling. Local tests should verify chunked application behavior without making process-memory assertions.
- Add or keep backend tests that upload generated files through validation and verify files are streamed to disk without loading all file bytes into an application-level list or bytes accumulator.
- The runtime assertion uses a fake upload file object whose `read(size)` records each requested `size` and raises if `size < 0`, `size is None`, or `size > 1024 * 1024`; the test asserts no raised error and `max(read_sizes) <= 1024 * 1024`.
- Add a backend test for a generated PDF over `MAX_PAGES_PER_FILE` to verify early `too_many_pages` rejection.
- Manual/CI does not need to process five 50 MiB files, but implementation must keep validation chunked and per-file limit enforcement independent.

Manual Compose:

Docker Compose remains optional deployment/manual-integration material and is not part of current development verification.

Manual golden path:

1. Open `http://localhost:5173`.
2. Enter token `dev-token`.
3. Upload three valid files:
   - `samples/purchase.png`
   - `samples/nohit.png`
   - `samples/very-long-contract-file-name-for-responsive-wrapping-check-abcdefghijklmnopqrstuvwxyz-0123456789.png`
4. Query `金额大于100万的合同`.
5. Submit task.
6. See progress timeline events for parse, qmd, classification, completion.
7. See `purchase.png` in `待复核合同` because structured comparison requires review.
8. See `nohit.png` in `待复核合同` with reason `no_evidence`.
9. See the long filename sample in `待复核合同`; open its evidence drawer and verify the long evidence text wraps without horizontal overflow.
10. Open evidence drawer for `purchase.png`.
11. Download `purchase.png`; verify browser saves a file.
12. Clear token, use `bad-token`, refresh task page, verify auth error.

Required manual release check for non-structured query:

1. Upload `samples/purchase.png`.
2. Query `合同总价`.
3. The result appears in `入选合同` with reason `keyword_evidence_matched`.
4. No result appears in `已排除合同`.

## 26. Required Tests

`test_upload_validation.py`:

- Accepts valid PDF.
- Rejects 0 files.
- Rejects 6 files.
- Rejects empty file.
- Rejects file larger than `MAX_UPLOAD_MB * 1024 * 1024` and accepts exactly-at-limit file.
- Rejects unsupported extension.
- Rejects MIME mismatch.
- Rejects content spoofing where readable image/PDF bytes do not match the validated extension, such as PNG bytes uploaded as `.jpg`.
- Accepts `application/octet-stream` when extension is allowed and persists inferred MIME.
- Rejects corrupt PDF.
- Rejects PDF over `MAX_PAGES_PER_FILE`.
- Rejects corrupt image.
- Rejects readable image bytes whose format does not match extension.
- Rejects images over `10000 x 10000` pixels, over `50_000_000` total pixels, or triggering Pillow decompression-bomb protection.
- Sanitizes basename and strips path traversal components.
- Preserves extension during 180-character truncation.
- Matches extensions case-insensitively and persists lowercase extension in display filenames.
- Adds duplicate filename suffixes `_2`, `_3` before extension.
- Validation failure leaves no task row.
- Upload validation streams from `UploadFile.file` in chunks no larger than 1 MiB and does not concatenate the full upload into memory.
- Five generated 5 MiB image uploads pass validation and persist all files without application-level full-file buffering.

`test_screening_plan.py`:

- Builds one `general_match` condition.
- Adds amount marker query.
- Marks structured query `金额大于100万的合同` as structured.
- Keeps `自动续约` non-structured.
- Deduplicates qmd queries.

`test_aggregator.py`:

- `persist_qmd_results(...)` maps qmd URI contract ID to contract and writes `qmd_mapping_failed` audit for unmapped candidates.
- Parses only the constrained qmd front matter format without PyYAML; malformed front matter falls through to unmapped handling.
- Treats a valid qmd task id from another task in URI or front matter as unmapped and writes `qmd_mapping_failed` with reason `wrong_task`.
- Treats a valid current-task qmd URI or front matter whose contract id is not in the current task as unmapped and writes `qmd_mapping_failed` with reason `unknown_contract`.
- `qmd_mapping_failed.payload.artifact_ref` is canonical `qmd://...` when safely derivable and `null` for local-path or invalid-URI cases.
- Drops unmapped candidates from classification.
- Extracts evidence text and score.
- Marks weak snippets as not counting toward evidence.
- Deduplicates evidence by `(contract_id, condition_id, artifact_ref, page, normalized_text)` and caps each condition at 5 evidence items.

`test_qmd_fixture.py`:

- Removes front matter before token matching so metadata cannot create false-positive hits.
- `NOHIT` documents return no candidates.
- Marker-token matching covers amount markers and marker/structured overlap rules.
- Results sort by `file_name` from constrained front matter, then `contract_id`.
- `top_k` limits returned fixture results after deterministic sorting.
- Blank `snippet` and `text` results are dropped before persistence.
- Fixture results synthesize non-null `QmdResult.raw` and persisted `raw_result` when fixture JSON omits `raw`.

`test_classifier.py`:

- Failed parse -> `uncertain/parse_failed`.
- Low quality -> `uncertain/low_quality_parse`.
- Structured with evidence -> `uncertain/structured_condition_requires_review`.
- Non-structured with evidence -> `included/keyword_evidence_matched`.
- No evidence -> `uncertain/no_evidence`.
- `parse_failed` emits empty matched conditions, all conditions missing, and empty evidence.
- `low_quality_parse` uses computed matched/missing conditions and available capped evidence.
- `structured_condition_requires_review` and `keyword_evidence_matched` return capped matched-condition evidence in plan order.
- Never emits `excluded`.

`test_api_vertical_slice.py`:

- POST upload returns task URLs.
- Results endpoint returns `200` with partial or empty buckets for active non-terminal tasks.
- Results endpoint performs stale-task mutation before returning buckets for a stale active task.
- Running `run_screening_task(task_id)` synchronously completes the task under fixture qmd and mocked/fake parser.
- Results endpoint returns included/uncertain/excluded buckets.
- Structured amount query returns uncertain result.
- All-files-parse-failed task ends `failed` and results endpoint returns `uncertain/parse_failed` items.
- Mixed parse success plus parse failure completes the task and returns one normal result plus one `uncertain/parse_failed` result.
- Mixed parse success plus low quality completes the task and returns the low-quality contract as `uncertain/low_quality_parse`.
- Artifact write failure after a previous file produced artifacts marks the task `failed/artifact_write_failed`, cleans partial artifacts for the failing file, and does not create result rows after the failure.
- `qmd_indexing.contract_count` counts only generated qmd docs and `qmd_retrieved.candidate_count` counts persisted nonblank qmd candidate rows before weak/unmapped filtering.
- Normal successful classification emits one `progress` event immediately after each `contract_classified`.

`test_sse_events.py`:

- Missing auth returns 401.
- Non-bearer auth returns 401.
- Invalid token returns 401.
- Valid other-owner token on an existing task returns 404 and writes `permission_denied`.
- Snapshot is sent when `Last-Event-ID` is absent.
- Reconnect with valid `Last-Event-ID` returns only later events.
- Reconnect with valid `Last-Event-ID` at or beyond a terminal event replays the latest terminal `task_completed` or `task_failed` event once and closes cleanly.
- Malformed, cross-task, negative, and non-integer `Last-Event-ID` each send a snapshot and replay persisted events from sequence 1.
- Events endpoint marks stale active task `failed/task_stale`, emits `task_failed`, and closes after terminal event.
- Stream closes after terminal event.
- SSE response includes `Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-cache`, `Connection: keep-alive`, and `X-Accel-Buffering: no`.
- Stream payloads match section 15 authoritative shapes, including `task_created.file_count`, `file_accepted.content_type`, `file_accepted.sha256`, and `task_failed.task_id`.
- Golden-path stream events for two successful files follow the exact event-type order in section 15.
- Status commits are visible in the database before their corresponding stream events, including `parsing` before `task_started`, `indexing` before `qmd_indexing`, `indexed` before `qmd_indexed`, `retrieving` before first `qmd_searching`, `classifying` before first `contract_classified`, and `completed` in the same transaction as `task_completed`.
- Progress events appear only at the section 15 points; no extra progress event is emitted solely for `parsed`, `indexing`, `retrieving`, or `completed`.
- All-files-parse-failed stream skips qmd events, emits `criteria_parsed`, emits `contract_classified`, emits classification progress, and ends with `task_failed/parse_all_failed`.
- All-files-parse-failed emits `criteria_parsed` while task status remains `parsing`, then switches to `classifying` before the first `contract_classified`.

`test_task_auth.py`:

- Malformed `APP_AUTH_TOKENS` entries fail settings validation.
- Empty or whitespace-only `APP_AUTH_TOKENS`, empty comma segments, and entries without exactly one colon fail settings validation.
- Token or owner ID longer than 128 characters fails settings validation.
- Duplicate tokens fail settings validation.
- `QMD_MODE=cli` fails settings validation with message `qmd cli mode is not implemented in Phase 1`; any other unsupported `QMD_MODE` also fails settings validation.
- Relative `STORAGE_ROOT` fails settings validation.
- Non-positive numeric limits fail settings validation.
- `MAX_FILES_PER_TASK` greater than 20 fails settings validation.
- `MAX_FILES_PER_TASK` not equal to `5` fails settings validation in Phase 1.
- `SSE_KEEPALIVE_SECONDS` outside 1 to 300 fails settings validation.
- Token and owner ID whitespace is trimmed.
- Duplicate owner IDs are allowed.
- Owner can read task summary.
- Owner can read task results.
- Other valid owner receives 404 for task summary and writes `permission_denied`.
- Other valid owner receives 404 for task results and writes `permission_denied`.
- Invalid token receives 401 for task summary, results, and events.
- Missing auth on `POST /api/screening-tasks` returns `401 auth_invalid` before multipart validation.
- Non-bearer auth on `POST /api/screening-tasks` returns `401 auth_invalid` before multipart validation.
- Invalid token on `POST /api/screening-tasks` returns `401 auth_invalid` before multipart validation.
- Unauthenticated `OPTIONS /api/screening-tasks` CORS preflight succeeds without bearer auth and includes CORS allow headers.
- Cross-origin invalid-token `GET /api/screening-tasks/{task_id}` returns `401 auth_invalid` with CORS allow-origin headers so the browser can read the error envelope.

`test_error_envelope.py`:

- Malformed UUID path parameter returns `422 invalid_request` standard envelope.
- Unknown route returns `404 not_found` standard envelope.
- Method not allowed returns `422 invalid_request` standard envelope.
- Malformed multipart body returns `422 invalid_request` standard envelope.
- Missing query returns `400 query_required` standard envelope.
- Blank query returns `400 query_required` standard envelope.
- Query longer than 1000 characters returns `400 query_too_long` standard envelope.
- Title longer than 120 characters returns `400 title_too_long` standard envelope.
- Generic FastAPI `RequestValidationError` returns `422 invalid_request` standard envelope.
- Unexpected unhandled exception returns `500 internal_error` standard envelope without exception text.

`test_unified_parser_client.py`:

- Successful response normalizes evidence by dropping entries with non-positive page numbers before constructing `ParseResult`.
- Successful response preserves parser name, parser version, quality, contract Markdown, page Markdown, valid evidence, and metadata.
- Duplicate `pages[].page_number` raises `parse_service_invalid_response`.
- Empty or over-128-character `parser_name` or `parser_version` raises `parse_service_invalid_response`.
- HTTP 4xx raises `ParseServiceFailed(error_code="parse_service_rejected", message="Parsing service rejected the file", retryable=False)` and is not retried.
- HTTP 5xx is retried exactly once, then raises `ParseServiceFailed(error_code="parse_service_unavailable", message="Parsing service unavailable", retryable=True)` if the retry also fails.
- Timeout is retried exactly once, then raises `ParseServiceFailed(error_code="parse_service_timeout", message="Parsing service request timed out", retryable=True)` if the retry also times out.
- Non-timeout transport errors such as connection refused are retried exactly once, then raise `ParseServiceFailed(error_code="parse_service_unavailable", message="Parsing service unavailable", retryable=True)`.
- Invalid JSON raises `ParseServiceFailed(error_code="parse_service_invalid_response", message="Parsing service returned an invalid response", retryable=False)`.
- Schema validation failure, including empty `pages`, non-positive `page_number`, invalid `bbox`, invalid `confidence`, or non-string `contract_markdown`, raises `parse_service_invalid_response`.
- Positive `metadata.page_count` differing from `len(pages)` returns a valid response but is later classified by low-quality rules; emitted/persisted page count uses `len(pages)`.
- Timeout or HTTP 5xx followed by a valid retry response returns the normalized parse response.
- Retryable first failure followed by a different terminal retry failure emits the retry attempt's final error code.
- HTTP 4xx, invalid JSON, and schema validation failures do not retry.

`test_download_auth.py`:

- Owner can download.
- Other valid owner receives 404 and writes `permission_denied`.
- Invalid token receives 401.
- Download response uses attachment content disposition.
- Stored path outside `STORAGE_ROOT` returns 404 and writes `permission_denied` with `reason=path_escape`.
- Missing stored file returns `404 download_file_missing` and does not write `download` audit.
- Unreadable/non-regular stored path returns `404 download_file_unreadable` and does not write `download` audit.

Optional `qmd_cli_contract_optional.py`:

- CLI mode constructs `collection add` command with global `--index`.
- CLI mode constructs `search --json -n ... -c task-{task_id}` command.
- CLI mode invokes `subprocess.run` with `shell=False` and argv list.
- User query containing shell metacharacters is passed as one argv element.
- CLI timeout raises `QmdCommandFailed`.
- Parses JSON array output.
- Parses newline-delimited JSON output.
- Non-zero exit raises `QmdCommandFailed`.

This optional contract file may be included in the repo, but it does not start with `test_` and is excluded from the default `pytest` gate unless an implementer explicitly enables CLI mode tests. The Phase 1 required gate is fixture qmd only.

`test_operational_risks.py`:

- Stale active task older than 1800 seconds becomes `failed/task_stale` on task summary read.
- Stale `uploaded` task older than 1800 seconds becomes `failed/task_stale` on task summary read.
- Duplicate `run_screening_task(task_id)` invocation after a task has been claimed from `uploaded` returns without duplicate stream events, artifacts, or results.
- Audit payloads do not contain bearer tokens, `stored_path`, full contract text, or local artifact paths.
- Successful parse writes `parse_succeeded` audit, parse failure writes `parse_failed` audit, and result creation writes `classification_completed` audit with required payload fields.
- Storage helper rejects path traversal outside `STORAGE_ROOT`.
- Parsed artifact helper rejects writes outside `STORAGE_ROOT`.
- Upload final-storage move failure cleans temporary/final files and leaves no task row.
- DB commit failure after upload final-storage move returns `500 storage_write_failed` and leaves any moved files in place as audit-only residue because commit outcome can be ambiguous.
- DB commit failure after parsed artifact final moves marks task `failed/artifact_write_failed`, emits/audits `task_failed`, leaves moved parsed/qmd files as audit-only residue, and creates no result rows.
- `parsed_artifacts` prevents duplicate contract-level artifacts using `page_number=0`.
- All-files-parse-failed path persists `ScreeningPlan`, emits `criteria_parsed`, emits `contract_classified`, ends task as `failed/parse_all_failed`, and keeps results readable.
- Task failure audit and stream payloads use the exact stage table from section 14.
- Unexpected worker exceptions after task claim mark the task `failed/worker_unexpected_error`, emit and audit `task_failed`, keep results endpoint readable, and do not expose exception text.
- Compose worker command uses `$$REDIS_URL` so Compose does not interpolate the host environment before container startup.

`test_schema_migration.py`:

- SQLAlchemy metadata can create all tables in SQLite with the same model columns used by tests.
- Alembic upgrade succeeds on PostgreSQL through Docker Compose.
- PostgreSQL round trip verifies UUID, JSON, and timezone-aware timestamp fields on representative task, contract, and result rows; this test is skipped in default local pytest unless `RUN_POSTGRES_TESTS=1` and `DATABASE_URL` is PostgreSQL. It is not part of the current development-stage verification gate.
- Model column names match the initial migration for all Phase 1 tables.

Frontend tests:

- Upload page disables submit until token, query, and file are present.
- Token input does not save while typing; clicking `保存 Token` saves the trimmed token and enables upload.
- Successful upload navigates to `/tasks/:taskId`.
- Task page renders progress events by `data-testid`.
- Task page renders latest event id as `data-testid="latest-event-id"`.
- Result buckets render all three headings.
- `ResultBuckets` passes `onOpenEvidence` to result cards; clicking a card evidence button opens the drawer owned by `TaskProgressPage`.
- Evidence drawer opens with `role="dialog"`, `aria-modal="true"`, accessible name `证据详情`, and initial focus on the close button.
- Evidence drawer closes on `Escape`, traps `Tab`/`Shift+Tab` focus within the drawer while open, and returns focus to the originating evidence button on close.
- Download function uses `Authorization` header and blob download path.
- 401 clears token.
- Task page aborts active SSE, clears polling intervals, and ignores queued result fetch completion after a 401.
- Task page renders `任务不存在或无权访问` for initial summary `404`.
- Task page renders `任务加载失败，请稍后重试` for initial summary 500, network error, or non-JSON failure without clearing token.
- Task page falls back to polling when SSE fails before a terminal event.
- Task page falls back to polling when `subscribeTaskEvents` reports `sse_stream_ended` before a terminal event.
- Task page renders `task-failure-banner` with safe `error_message` and `error_code` when polled summary status becomes `failed`.
- Task page renders `task-failure-banner` when an SSE `task_failed` event is received and final summary/results are fetched.
- `subscribeTaskEvents` calls `onEvent` before `onComplete` for terminal events and converts non-2xx SSE error envelopes into `ApiError`.
- `subscribeTaskEvents` sends `Last-Event-ID` when provided, ignores keepalive comments, handles partial chunks, accepts CRLF, and joins multi-line `data:` frames before JSON parsing.

## 27. README Requirements

`.gitignore` must include:

```text
.env
.venv/
samples/
__pycache__/
.pytest_cache/
node_modules/
dist/
```

Docker build-context hygiene:

- `backend/.dockerignore` must include `.venv/`, `__pycache__/`, `.pytest_cache/`, and `tests/`.
- `frontend/.dockerignore` must include `node_modules/`, `dist/`, `test-results/`, and `playwright-report/`.

`README.md` must include:

- Project purpose in Chinese.
- Development-stage local verification commands:

```sh
cd backend
../.venv/bin/pytest
cd ../frontend
npm test -- --run
npm run build
```

- Optional manual integration may document Docker Compose separately, but Docker/Compose must not be described as the required development verification path.
- Open `http://localhost:5173` when a frontend dev server is running.
- Development token: `dev-token`.
- Phase 1 limitations:
  - fixture qmd is default.
  - qmd CLI is a future/reference adapter contract and is rejected by shipped Phase 1 settings.
  - parsing is delegated to the enterprise unified parsing service or a custom compatible parsing service through `PARSING_SERVICE_URL`; this repository does not operate a production OCR service.
  - no automatic excluded.
  - no export/review/history.

## 28. External Integration Notes

qmd current public README describes qmd as a local search engine for Markdown documents with BM25, vector semantic search, and LLM reranking. It supports CLI installation through `@tobilu/qmd`, collection add, JSON output, collection-scoped search, and MCP/SDK options. Shipped Phase 1 uses the fixture qmd adapter only; the CLI `search --json` command in section 17.2 is a future/reference adapter contract and deliberately avoids qmd `query` so later CLI work does not require local LLM reranking.

Document parsing integration is represented by a strict HTTP adapter in this repo. Parsing is expected to be provided by the enterprise unified parsing service or a custom compatible parsing service, and this project stores the provider request id, parser metadata, quality summary, normalized pages, normalized evidence, and artifact paths needed for contract-screening auditability.

## 29. Known Limitations

- Phase 1 is recall-oriented and conservative; many useful results will be `uncertain`.
- Structured conditions such as amount/date comparisons are not automatically verified.
- qmd CLI mode is not a production guarantee.
- The app has token-based auth only.
- There is no durable task history UI.
- There is no export.
- There is no human review endpoint.
- There is no direct integration with an existing enterprise contract repository.
- The repository does not own production document parsing; parse quality and SLA depend on the enterprise unified parsing service.

## 30. Implementation Order After Gates Pass

1. Backend project scaffold, config, errors, DB, models, migration.
2. Storage and upload validation.
3. Auth and API routes.
4. Stream/audit helpers.
5. Unified parsing service adapter and fake parser test double.
6. qmd fixture/CLI adapter.
7. Screening plan, aggregation, classifier.
8. Worker pipeline.
9. Backend tests.
10. Frontend scaffold, API client, SSE client.
11. Frontend pages/components.
12. Frontend tests.
13. Docker Compose and README.
14. Full verification commands and manual walkthrough.

## 31. Hard Gate Status

This section is a process guard, not an implementation requirement.

Independent Pass B Critic and Pass C Readiness agents evaluated whether the engineering specification above is complete enough for implementation.

Gate results on 2026-06-21:

- Pass B Critic: `design ready`.
- Pass C Implementation Readiness: `implementation ready`.

Implementation may proceed with section 30.

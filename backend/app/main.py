from pathlib import Path
import os
import sys


def _ensure_backend_import_root() -> None:
    backend_app_root = Path(__file__).resolve().parent
    repo_app_root = backend_app_root.parent.parent / "app"
    backend_root = str(backend_app_root.parent)
    loaded_app = sys.modules.get("app")
    loaded_app_file_value = getattr(loaded_app, "__file__", None) if loaded_app else None
    loaded_app_file = Path(loaded_app_file_value).resolve() if loaded_app_file_value else None
    loaded_app_paths = [Path(path).resolve() for path in getattr(loaded_app, "__path__", [])] if loaded_app else []

    file_is_local = loaded_app_file is not None and (
        loaded_app_file.is_relative_to(backend_app_root) or loaded_app_file.is_relative_to(repo_app_root)
    )
    paths_are_local = bool(loaded_app_paths) and all(
        path.is_relative_to(backend_app_root) or path.is_relative_to(repo_app_root) for path in loaded_app_paths
    )
    if loaded_app and not (file_is_local or paths_are_local):
        for name in list(sys.modules):
            if name == __name__:
                continue
            if name == "app" or name.startswith("app."):
                del sys.modules[name]
    if backend_root in sys.path:
        sys.path.remove(backend_root)
    sys.path.insert(0, backend_root)


_ensure_backend_import_root()

try:
    from fastapi import FastAPI

    from app.api.auth import ApiAuthMiddleware
    from app.api import contracts, health, qmd_documents, screening_tasks
    from app.errors import register_error_handlers
except ModuleNotFoundError as exc:
    if exc.name in {"fastapi", "pydantic_settings", "sqlalchemy", "pydantic"}:
        raise RuntimeError(
            "Backend Python dependencies are missing. Run: "
            'python3.12 -m pip install -e "backend[dev]"'
        ) from exc
    raise


def create_app() -> FastAPI:
    app = FastAPI(title="Contract Screening Agent", version="0.1.0")
    register_error_handlers(app)
    app.add_middleware(ApiAuthMiddleware)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    app.include_router(screening_tasks.router, prefix="/api/screening-tasks", tags=["screening_tasks"])
    app.include_router(qmd_documents.router, prefix="/api/qmd-documents", tags=["qmd-documents"])
    app.include_router(contracts.router, prefix="/api/contracts", tags=["contracts"])
    app.include_router(health.router, prefix="/api", tags=["health"])
    return app


app = create_app()


def run_dev_server() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("CONTRACT_AGENT_HOST", "127.0.0.1"),
        port=int(os.getenv("CONTRACT_AGENT_PORT", "8000")),
        log_level=os.getenv("CONTRACT_AGENT_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    run_dev_server()

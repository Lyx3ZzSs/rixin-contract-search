import os
import subprocess
import sys
from pathlib import Path


def test_main_direct_execution_prefers_local_backend_app(tmp_path):
    fake_app = tmp_path / "app"
    fake_app.mkdir()
    (fake_app / "__init__.py").write_text("raise RuntimeError('wrong app imported')\n", encoding="utf-8")
    (tmp_path / "uvicorn.py").write_text(
        "def run(app, **kwargs):\n"
        "    print(app.title)\n"
        "    print(kwargs['host'])\n"
        "    print(kwargs['port'])\n",
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[2]
    main_py = repo_root / "backend" / "app" / "main.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)
    env["CONTRACT_AGENT_HOST"] = "127.0.0.1"
    env["CONTRACT_AGENT_PORT"] = "18080"

    result = subprocess.run(
        [sys.executable, str(main_py)],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "Contract Screening Agent" in result.stdout
    assert "127.0.0.1" in result.stdout
    assert "18080" in result.stdout


def test_main_import_clears_preloaded_wrong_app(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    main_py = repo_root / "backend" / "app" / "main.py"
    code = f"""
import importlib.util
import pathlib
import sys
import types

wrong_app = types.ModuleType("app")
wrong_app.__file__ = "/tmp/wrong-app/app/__init__.py"
wrong_app.__path__ = ["/tmp/wrong-app/app"]
sys.modules["app"] = wrong_app

spec = importlib.util.spec_from_file_location("local_backend_main", pathlib.Path({str(main_py)!r}))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.app.title)
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "Contract Screening Agent" in result.stdout


def test_main_import_clears_preloaded_wrong_namespace_app(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    main_py = repo_root / "backend" / "app" / "main.py"
    code = f"""
import importlib.util
import pathlib
import sys
import types

wrong_app = types.ModuleType("app")
wrong_app.__file__ = None
wrong_app.__path__ = ["/tmp/wrong-namespace-app/app"]
sys.modules["app"] = wrong_app

spec = importlib.util.spec_from_file_location("local_backend_main", pathlib.Path({str(main_py)!r}))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.app.title)
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "Contract Screening Agent" in result.stdout


def test_root_import_prefers_local_backend_app(tmp_path):
    fake_app = tmp_path / "app"
    fake_app.mkdir()
    (fake_app / "__init__.py").write_text("raise RuntimeError('wrong app imported')\n", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)

    result = subprocess.run(
        [sys.executable, "-c", "import app.main; print(app.main.app.title)"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "Contract Screening Agent" in result.stdout


def test_root_import_preserves_in_flight_main_when_wrong_app_preloaded():
    repo_root = Path(__file__).resolve().parents[2]
    code = """
import sys
import types

wrong_app = types.ModuleType("app")
wrong_app.__file__ = None
wrong_app.__path__ = ["/tmp/wrong-namespace-app/app"]
sys.modules["app"] = wrong_app

import app.main
print(app.main.app.title)
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "Contract Screening Agent" in result.stdout

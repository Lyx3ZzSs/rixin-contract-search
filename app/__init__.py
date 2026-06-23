from pathlib import Path

_backend_app = Path(__file__).resolve().parents[1] / "backend" / "app"
__path__ = [str(_backend_app), *__path__]

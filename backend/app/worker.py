import json
import sys

from redis import Redis
from rq import SimpleWorker, Worker

from app.config import settings


def choose_worker_class(mode: str):
    mode = mode.strip()
    if mode == "simple":
        return SimpleWorker
    if mode == "fork":
        return Worker
    if mode == "auto":
        return SimpleWorker if sys.platform == "darwin" else Worker
    raise ValueError("RQ_WORKER_MODE must be auto, simple, or fork")


def main() -> None:
    worker_class = choose_worker_class(settings.RQ_WORKER_MODE)
    print(json.dumps(settings.redacted_runtime_status(), ensure_ascii=False, sort_keys=True))
    worker = worker_class(["screening"], connection=Redis.from_url(settings.REDIS_URL))
    worker.work()


if __name__ == "__main__":
    main()

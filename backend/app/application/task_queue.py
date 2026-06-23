from uuid import UUID

from redis import Redis
from rq import Queue

from app.config import settings


def enqueue_screening_task(task_id: UUID) -> str:
    from app.application.screening_runner import run_screening_task

    queue = Queue("screening", connection=Redis.from_url(settings.REDIS_URL), default_timeout=1800)
    job = queue.enqueue(run_screening_task, str(task_id), retry=None)
    return job.id

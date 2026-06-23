from redis import Redis
from rq import Worker

from app.config import settings


def main() -> None:
    worker = Worker(["screening"], connection=Redis.from_url(settings.REDIS_URL))
    worker.work()


if __name__ == "__main__":
    main()


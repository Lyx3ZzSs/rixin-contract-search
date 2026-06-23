FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic
RUN pip install -e .
EXPOSE 8000


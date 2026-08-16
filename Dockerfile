# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.9.7

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM dependencies AS application
COPY . .
RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
RUN mkdir -p /app/agent-dist && \
    uv build agent --wheel --out-dir /app/agent-dist
RUN EXECUTION_MODE=build python manage.py collectstatic --noinput

FROM dependencies AS test-dependencies
RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

FROM test-dependencies AS test
COPY . .
RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    uv sync --frozen
RUN mkdir -p /app/agent-dist && \
    uv build agent --wheel --out-dir /app/agent-dist
RUN chown -R nobody:nogroup /app
USER nobody
CMD ["pytest", "--cov", "--cov-report=term-missing"]

FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH \
    PORT=80
WORKDIR /app

RUN addgroup --system app && \
    adduser --system --ingroup app --shell /bin/bash --home /app --no-create-home app

COPY --from=dependencies --chown=app:app /app/.venv /app/.venv
COPY --from=application --chown=app:app /app/kiosk_manager /app/kiosk_manager
COPY --from=application --chown=app:app /app/manage.py /app/manage.py
COPY --from=application --chown=app:app /app/runserver.sh /app/runserver.sh
COPY --from=application --chown=app:app /app/aldryn-celery.sh /app/.venv/bin/aldryn-celery
COPY --from=application --chown=app:app /app/agent-dist /app/agent-dist
COPY --from=application --chown=app:app /app/templates /app/templates
COPY --from=application --chown=app:app /app/staticfiles /app/staticfiles
RUN mkdir -p /app/media && chown -R app:app /app/media

USER app
EXPOSE 80

CMD ["./runserver.sh"]

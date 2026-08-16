#!/bin/sh
set -eu

exec uvicorn \
    --host=0.0.0.0 \
    --port="${PORT:-80}" \
    --lifespan=off \
    --log-level="${UVICORN_LOG_LEVEL:-info}" \
    kiosk_manager.asgi:application

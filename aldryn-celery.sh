#!/bin/sh
set -eu

: "${CELERY_APP:=kiosk_manager.celery.app:app}"

command="${1:-worker}"
shift || true

case "$command" in
beat)
    exec celery -A "$CELERY_APP" beat --loglevel=INFO "$@"
    ;;
worker)
    exec celery -A "$CELERY_APP" \
        worker \
        --without-gossip \
        --without-mingle \
        --without-heartbeat \
        --concurrency="${CELERY_WORKER_CONCURRENCY:-1}" \
        --loglevel=INFO \
        "$@"
    ;;
*)
    echo "usage: aldryn-celery.sh {worker|beat} [args...]" >&2
    exit 2
    ;;
esac

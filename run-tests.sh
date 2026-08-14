#!/bin/sh
set -eu

uv run python manage.py migrate --noinput
exec uv run pytest --cov --cov-report=term-missing

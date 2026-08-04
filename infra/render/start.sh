#!/bin/sh
set -eu

alembic upgrade head
python -m sawtai.seed
exec uvicorn sawtai.main:app --host 0.0.0.0 --port "${PORT:-10000}"

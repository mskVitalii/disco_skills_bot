#!/bin/sh
set -e

echo ">>> Running DB migrations..."
i=0
while ! uv run aerich upgrade; do
  i=$((i+1))
  if [ "$i" -ge 10 ]; then
    echo "ERROR: DB not ready after 10 attempts — aborting"
    exit 1
  fi
  echo "DB not ready, retrying in 5s ($i/10)..."
  sleep 5
done
echo ">>> Migrations done"

exec uv run uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"

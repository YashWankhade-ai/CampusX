#!/bin/bash
set -e

# Wait for DB
echo "Waiting for postgres..."
while ! nc -z db 5432; do
  sleep 0.1
done
echo "PostgreSQL started"

# Run migrations
flask db upgrade

exec "$@"

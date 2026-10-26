#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for postgres..."
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"

python -c "
import socket
import time
import sys
import os

db_url = os.environ.get('DATABASE_URL', '')
host = '$DB_HOST'
port = int('$DB_PORT')

if 'sqlite' in db_url.lower():
    print('SQLite database in use; skipping network wait.')
    sys.exit(0)

timeout = 45
start = time.time()

while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f'PostgreSQL is ready at {host}:{port}')
            sys.exit(0)
    except Exception:
        if time.time() - start > timeout:
            print(f'Notice: proceeding after waiting for PostgreSQL at {host}:{port}', file=sys.stderr)
            sys.exit(0)
        time.sleep(0.5)
"

exec "$@"

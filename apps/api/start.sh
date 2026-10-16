#!/bin/sh
# Container entrypoint. Only the api role runs migrations, so the two services never race.
set -e

if [ "$SERVICE_ROLE" = "worker" ]; then
    exec python -m bide_followup.worker
fi

# The database may not be reachable for a moment (a restart, a redeploy, Railway's private network warming up):
# retry for up to a minute rather than crash.
tries=0
until alembic upgrade head; do
    tries=$((tries + 1))
    if [ "$tries" -ge 30 ]; then
        echo "database still unreachable after $tries tries; giving up" >&2
        exit 1
    fi
    echo "database not ready; retrying in 2s ($tries/30)" >&2
    sleep 2
done
python -m bide_followup.seed
exec uvicorn bide_followup.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips '*'

#!/bin/sh
set -eu

export PGPASSWORD=hotel_password
export DATABASE_URL=postgresql+psycopg://hotel_user:hotel_password@postgres:5432/hotel_booking
export TEST_DATABASE_URL=postgresql+psycopg://hotel_user:hotel_password@postgres:5432/hotel_booking_test
mkdir -p /tmp/project /tmp/pgdata /tmp/pgsocket
printf '%s\n' "$PGPASSWORD" >/tmp/pgpassword
initdb -D /tmp/pgdata --username=hotel_user --pwfile=/tmp/pgpassword --auth=scram-sha-256 >/tmp/pg-init.log
pg_ctl -D /tmp/pgdata -o '-h 127.0.0.1 -k /tmp/pgsocket' -w start >/tmp/pg-start.log
app_pid=
cleanup() {
    if [ -n "$app_pid" ]; then kill "$app_pid" 2>/dev/null || true; fi
    pg_ctl -D /tmp/pgdata -m fast -w stop >/dev/null 2>&1 || true
}
trap cleanup EXIT
createdb -h /tmp/pgsocket -U hotel_user hotel_booking
python - <<'PY'
from pathlib import Path, PurePosixPath
import shutil
import tarfile

root = Path("/tmp/project")
with tarfile.open("/forgeai-input/source.tar.gz", "r:gz") as archive:
    total = 0
    for member in archive:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile()):
            raise SystemExit(f"Unsupported source archive entry: {member.name}")
        target = root / path
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        total += member.size
        if total > 256 * 1024 * 1024:
            raise SystemExit("Expanded source snapshot exceeds 256 MiB.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.extractfile(member) as source, target.open("xb") as output:
            shutil.copyfileobj(source, output)
        target.chmod(0o755 if member.mode & 0o111 else 0o644)
PY
cd /tmp/project
python -m uvicorn "$APP_IMPORT" --host 127.0.0.1 --port 8000 >/tmp/app.log 2>&1 &
app_pid=$!
if ! python - <<'PY'
import os
import time
from urllib.request import urlopen

for _ in range(30):
    try:
        with urlopen("http://127.0.0.1:8000" + os.environ["HEALTH_PATH"], timeout=1) as response:
            if response.status == 200:
                print("Application startup and health endpoint passed.")
                break
    except OSError:
        pass
    time.sleep(1)
else:
    raise SystemExit("Application health check failed.")
PY
then
    tail -60 /tmp/app.log
    exit 1
fi
kill "$app_pid"
wait "$app_pid" || true
app_pid=
set -- -q -p no:cacheprovider
if [ -n "$PYTEST_IGNORE" ]; then
    printf 'External integration excluded from offline suite: %s\n' "$PYTEST_IGNORE"
    set -- "$@" "--ignore=$PYTEST_IGNORE"
fi
python -m pytest "$@"

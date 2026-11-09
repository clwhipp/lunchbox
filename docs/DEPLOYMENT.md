# Deployment and operations

## Configuration

Compose reads `.env`, which is excluded from source control and Docker's build context. The runtime image contains no secret. Keep the generated local key across restarts.

| Variable | Default/example | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Required private random string | Django signing/CSRF protection |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma-separated allowed hostnames/IPs without ports |
| `DJANGO_DEBUG` | `false` | Keep false in deployment |
| `SCHOOL_TIME_ZONE` | `America/Chicago` | Current local calendar week |
| `SCHOOL` | `NORTHEAST_ELEMENTARY` | Initial enum name from the provider client |
| `GRADE` | `01` | Initial upstream grade, kept as a string |
| `SUPPORTED_GRADES` | `01` | Verified grade codes offered in the selector |
| `BIND_ADDRESS` | `127.0.0.1` | Host network interface |
| `APP_PORT` | `8000` | Published host port |
| `DATABASE_PATH` | `/data/schoolcafe.sqlite3` | Set inside Compose's persistent data directory |
| `CSRF_TRUSTED_ORIGINS` | Empty | Optional trusted full origins for a proxy configuration |

Published menus cache for 15 minutes; empty menus for 5 minutes; saved-data fallback lasts at most 24 hours. Provider calls are paced across the single process, use a 5-second timeout, and retry transient connection/server errors once. HTTP 429 is not retried. Policy constants live in `schoolmenu/config/settings.py`.

This version uses one Gunicorn process, four threads, and local SQLite storage. Food identity is scoped to school and source item ID. Preferences persist across dates/grades within that school and are shared by the default child profile.

## Installation and household access

Follow the root README. Migrate explicitly before starting; startup rejects an unmigrated database.

```bash
docker compose run --rm web python manage.py migrate --noinput
docker compose up -d --wait
docker compose ps
docker compose logs --tail=50 web
```

Readiness checks SQLite access and migrations without contacting SchoolCafe. A live menu requires SchoolCafe when no fresh/saved response exists.

For another household device, set `BIND_ADDRESS=0.0.0.0`, add the computer's LAN IP/hostname to `DJANGO_ALLOWED_HOSTS`, and run `docker compose up -d --force-recreate --wait`. Visit `http://<computer-lan-ip>:8000` on that network; configure the host firewall as needed. For an HTTPS proxy, configure the trusted hostname/origin and terminate TLS/access control at the proxy. The initial deployment is local.

## Backups and restore

The backup command uses SQLite's online backup facility for a consistent view of WAL writes. Use a new filename each time; existing destinations are rejected.

```bash
docker compose exec web python manage.py backup /data/lunchbox-backup-2026-11-08.sqlite3
docker compose cp web:/data/lunchbox-backup-2026-11-08.sqlite3 ./lunchbox-backup-2026-11-08.sqlite3
```

Store the copied backup independently of the volume. To restore, stop the service and copy into a **new** database filename, avoiding WAL files from the old database:

```bash
docker compose stop web
docker compose run --rm --no-deps -T web python -c 'import sys; from pathlib import Path; p=Path("/data/restored.sqlite3"); p.open("xb").write(sys.stdin.buffer.read())' < ./lunchbox-backup-2026-11-08.sqlite3
# Change DATABASE_PATH in compose.yaml to /data/restored.sqlite3.
docker compose run --rm web python manage.py migrate --noinput
docker compose up -d --force-recreate --wait
```

The copy refuses to overwrite an existing file. Retain the previous database until restored preferences are checked. The smoke test verifies backup integrity and both preference states in a restored database.

## Updates and maintenance

Back up, build the new image, stop the old service, migrate with the new image, and start it:

```bash
docker compose build
docker compose stop web
docker compose run --rm web python manage.py migrate --noinput
docker compose up -d --wait
```

For a future incompatible migration, rollback needs the matching database backup and image. This initial release has one schema migration.

Run `docker compose exec web python manage.py prune_cache` to remove responses fetched over 90 days ago, retaining food identities/preferences. Ordinary `docker compose down` retains the volume. Adding `--volumes` deletes persisted data; the smoke script uses that only for its uniquely named disposable project.

## Verification

CI is configured for Python checks on 3.13/3.14, custom JavaScript coverage, browser acceptance, production-image persistence checks, and tests inside the Python 3.13 image. Browser tests use recorded API responses; production uses SchoolCafe.

`scripts/docker_smoke.py` verifies initial volume permissions, rejected unmigrated startup, UID 10001, real CSRF-protected HTTP saves, green/red states, nutrient details, persistence through restart/recreation, and backup restoration. It seeds the ordinary cache directly without introducing a production test mode. Only its own test project/volume is removed.

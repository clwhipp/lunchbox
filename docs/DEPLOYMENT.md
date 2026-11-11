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
| `SUPPORTED_GRADES` | `01,02,03,04,05` | Grade codes offered in the selector; 01–05 verified against Northeast Elementary |
| `BIND_ADDRESS` | `127.0.0.1` | Host network interface |
| `APP_PORT` | `8000` | Published host port |
| `LUNCHBOX_IMAGE` | `lunchbox:local` | Local image or published `username/lunchbox:version` to run |
| `DATABASE_PATH` | `/data/schoolcafe.sqlite3` | Set inside Compose's persistent data directory |
| `CSRF_TRUSTED_ORIGINS` | Empty | Optional trusted full origins for a proxy configuration |
| `CALENDAR_PUBLIC_BASE_URL` | Empty | Optional externally reachable HTTPS base URL for stable iPhone subscription links; allow a path prefix |
| `CALENDAR_REFRESH_INTERVAL_SECONDS` | `21600` | Interval in seconds between two-week cache refreshes; valid range 60–604800 |

Published menus cache for 15 minutes; empty menus for 5 minutes; saved-data fallback lasts at most 24 hours. Provider calls are paced across the single process, use a 5-second timeout, and retry transient connection/server errors once. HTTP 429 is not retried. Policy constants live in `schoolmenu/config/settings.py`.

This version uses one Gunicorn process, four threads, and local SQLite storage. Food identity is scoped to school and source item ID. Likes/dislikes persist across dates/grades within that school; sack-lunch confirmations are explicit weekday selections scoped to the child profile, school, and serving date, and therefore remain selected when the menu grade changes.

## Menu calendar subscription

The menu page's **Subscribe to menu calendar** button opens a details modal. Pressing **Show subscription URL** inside that modal reveals a stable `.ics` subscription URL; the revealed field includes a copy-to-clipboard button. The page uses a GET fallback to show the details when JavaScript is disabled. The feed is tied to the deployment-configured `SCHOOL` and `GRADE`; changing the page's school/grade selectors does not change this feed. It contains the ten weekdays within the next fourteen calendar days, using all school-week menu records that overlap that rolling window. Events are all-day, titled with weekday, abbreviated month and day, school, and grade. Descriptions group foods under `MAIN ENTRÉES`, `🥦 SIDES`, and `🥛 MILK & DRINKS`, mark liked items with `✅` and disliked items with `❌`, nest served-together choices beneath their entrée, and finish with `📋 FULL MENU` and the URL for that week's Lunchbox menu. The iCalendar `URL` property makes that same weekly page a tappable event link. Unpublished dates remain present with a placeholder. Like/dislike markers are read from the household's saved preferences when the feed is fetched.

The `calendar-refresh` Compose worker starts after the web service is healthy, immediately refreshes every school week intersecting the next fourteen days (normally two or three weeks), and repeats every `CALENDAR_REFRESH_INTERVAL_SECONDS` (default six hours). It shares the existing SQLite volume, publishes no port, and runs as UID/GID 10001 with a read-only image filesystem, a small `/tmp` tmpfs, no added capabilities, and bounded CPU/memory/PID resources. A failed pass is logged and retried after the next interval; an existing saved menu remains available. iPhone Calendar decides when it polls the subscribed URL, so the app cannot force immediate refresh on the device.

Set `CALENDAR_PUBLIC_BASE_URL` to the externally reachable HTTPS base URL when TLS terminates at a reverse proxy (for example, `https://menus.example.net`); an optional path prefix is supported. This keeps the copied URL usable from iPhone even if the proxy does not forward the original scheme. If unset, Lunchbox builds the address from the request that rendered the page. Ensure the public hostname is allowed by `DJANGO_ALLOWED_HOSTS` and that the route is reachable over HTTPS. Paste the copied URL into the iPhone Calendar app's **Add Subscribed Calendar** flow.

Treat the URL as a private bearer link: anyone who obtains it can see the household menu and like/dislike markers. Its path contains a short 22-character opaque HMAC token, with no embedded payload, keyed by `DJANGO_SECRET_KEY` and bound to `SCHOOL`/`GRADE`; changing the key or either default invalidates the old URL, so reveal and copy the new one from the menu page. Gunicorn access logs omit request targets to avoid recording the calendar token. Reverse-proxy logs may still record request paths; restrict access to those logs or redact `/calendar/` paths there.

Inspect worker activity with `docker compose logs --tail=100 calendar-refresh`. Run a single diagnostic refresh with:

```bash
docker compose run --rm --no-deps calendar-refresh python manage.py refresh_calendar_menus --once
```

## Installation and household access

Follow the root README. Migrate explicitly before starting; startup rejects an unmigrated database.

```bash
docker compose run --rm web python manage.py migrate --noinput
docker compose up -d --wait
docker compose ps
docker compose logs --tail=50 web
```

Readiness checks SQLite access and migrations without contacting SchoolCafe. A live menu requires SchoolCafe when no fresh/saved response exists.

For another household device on the LAN or tailnet, set `BIND_ADDRESS=0.0.0.0`, add the LAN IP/hostname or Tailscale IP/MagicDNS hostname to `DJANGO_ALLOWED_HOSTS`, and run `docker compose up -d --force-recreate --wait`. Visit `http://<address>:8000`. Binding to `0.0.0.0` publishes on all host IPv4 interfaces, not just Tailscale; configure the host firewall for the intended access. For an HTTPS proxy, configure the trusted hostname/origin and terminate TLS/access control at the proxy. The initial deployment is local.

## Docker Hub releases

The release workflow uses the same secret names and version-tag trigger as `poke-games`, publishing a single Linux/amd64 runtime image named **lunchbox**. All application, coverage, browser, Docker persistence, and workflow checks run through the reusable `ci.yml` workflow before the publishing job can log in and push. Branch pushes and pull requests run validation without publishing images.

Configure these secrets in the `clwhipp/lunchbox` GitHub repository under **Settings → Secrets and variables → Actions**:

| Secret | Value |
| --- | --- |
| `DOCKER_USERNAME` | The Docker Hub account that owns the `lunchbox` repository |
| `DOCKER_PASSWORD` | A Docker Hub access token with permission to push to that repository |

Repository secrets from `poke-games` are not copied by the workflow. Configure them in `lunchbox`, or grant this repository access to the existing organization secrets. Create the `lunchbox` repository in Docker Hub with the desired visibility. Credentials belong in GitHub secrets, not `.env`, Docker build arguments, or source files.

After the workflow changes have been committed and pushed, publish a release by pushing its tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

For a stable release, Docker's [metadata action](https://github.com/docker/metadata-action#semver) generates `username/lunchbox:1.0.0` and `username/lunchbox:latest`. A prerelease such as `v1.1.0-rc.1` generates the prerelease tag without changing `latest`. The Dockerfile's `runtime` target is published; test dependencies and the household database are excluded. A failed validation job prevents publication. Each release tag must reference the commit containing the intended source and workflow files.

To deploy the image, set `LUNCHBOX_IMAGE=your-dockerhub-username/lunchbox:1.0.0` in `.env`. For a private repository, log in to Docker Hub on the deployment host before pulling. A fresh installation uses:

```bash
docker compose pull web
docker compose run --rm --no-build web python manage.py migrate --noinput
docker compose up -d --no-build --wait
```

The `--no-build` flags run the pulled image. The same `schoolcafe_data` volume persists preferences. To update an existing installation, make a backup first, select the new version in `.env`, then:

```bash
docker compose pull web
docker compose stop web
docker compose run --rm --no-build web python manage.py migrate --noinput
docker compose up -d --no-build --wait
```

Use an explicit version when reproducible deployment matters. To build from source locally, select `LUNCHBOX_IMAGE=lunchbox:local` and use the build procedure below. The image naming change does not rename the existing SQLite volume.

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

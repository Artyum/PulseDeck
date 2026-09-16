# PulseDeck

A self-hosted support desk and ticket portal for teams and clients. Projects, tickets, comments, email notifications, and a bilingual UI — built with FastAPI and PostgreSQL.

## About

PulseDeck is a lightweight helpdesk for homelabs and small teams: staff manage projects and tickets in a portal, clients see only what they are allowed to, and email keeps everyone in the loop.

**What it does:**

- Multi-project ticket portal with human-readable URLs (`/p/{key}`, `/t/{key}-{number}`)
- Ticket types, statuses, priorities, tags, assignees, and participants
- Rich-text comments (Markdown) with internal notes for staff
- User roles: client, staff, admin
- Email notifications with an outbox worker (SMTP)
- Magic reply links for clients without a full account
- Bilingual UI (English / Polish; English by default)
- Multiple color themes with light/dark pairs
- PWA basics (service worker, offline page)
- Ships as a Docker image published to GHCR

**What it does not do:**

- No SaaS multi-tenancy — one deployment, one organization
- No built-in PostgreSQL container in production compose — bring your own database
- No LDAP/OAuth — session login with email and password

## How to use

### First-time setup

1. Copy the example env file:

   ```bash
   cp deploy/example/.env.dev.example deploy/.env.dev
   ```

2. Set `DATABASE_URL` to a PostgreSQL instance and choose a strong `STORAGE_SECRET`.

3. Start the stack (see [Development](#development) or [Running](#running) below).

4. Open the app in a browser and sign in with the bootstrap admin from `ADMIN_EMAIL` / `ADMIN_PASSWORD` in your env file.

5. Configure SMTP and portal settings in the admin UI (or seed them in env for first bootstrap).

### Portal

- **Feed** — filter and sort tickets per project (open, done, waiting on client, unassigned, and more)
- **Ticket** — description, comments, attachments, status changes, assignee, tags
- **Profile** — language, timezone, date format, theme
- **Reply link** — clients can answer from email without logging in (time-limited token)

### Admin

- **Users** — create, activate, block, assign roles
- **Projects** — keys, members, staff, enable/disable
- **Settings** — SMTP, upload limits, ticket reopen window, auth link TTL

### Environment variables

| Variable                  | Default                             | Description                                          |
| ------------------------- | ----------------------------------- | ---------------------------------------------------- |
| `DATABASE_URL`            | —                                   | PostgreSQL SQLAlchemy URL (required)                 |
| `STORAGE_SECRET`          | dev placeholder                     | Session signing secret; must be strong in production |
| `ENVIRONMENT`             | `dev`                               | `dev`, `preprod`, or `prod`                          |
| `APP_BASE_URL`            | `http://localhost:8000`             | Public base URL for links in email                   |
| `ALLOWED_HOSTS`           | `localhost,127.0.0.1,pulsedeck.lan` | Comma-separated trusted hostnames                    |
| `ADMIN_EMAIL`             | —                                   | Bootstrap admin email (first run)                    |
| `ADMIN_PASSWORD`          | —                                   | Bootstrap admin password (first run)                 |
| `SMTP_SERVER`             | empty                               | SMTP host; leave empty to disable outbound mail      |
| `SMTP_PORT`               | `587`                               | SMTP port                                            |
| `SMTP_USER` / `SMTP_PASS` | empty                               | SMTP credentials                                     |
| `EMAIL_FROM`              | empty                               | From address for outbound mail                       |
| `UVICORN_HOST`            | `127.0.0.1`                         | Bind address inside container                        |
| `UVICORN_PORT`            | `8000`                              | HTTP port                                            |
| `UVICORN_WORKERS`         | `1`                                 | Uvicorn worker processes                             |
| `UVICORN_PROXY_HEADERS`   | `false`                             | Enable when behind a reverse proxy                   |
| `SESSION_MAX_AGE_SECONDS` | `28800`                             | Session cookie lifetime                              |
| `TICKET_REOPEN_DAYS`      | `7`                                 | Days after close when clients may reopen             |

See [`deploy/example/.env.dev.example`](deploy/example/.env.dev.example) and [`deploy/example/.env.prod.example`](deploy/example/.env.prod.example) for the full list.

## Running

### Docker Compose (production / homelab)

Production compose lives under [`deploy/example/`](deploy/example/). It expects an external PostgreSQL database and runs three services: `migrate`, `web`, and `worker` (email outbox).

```bash
cp deploy/example/.env.prod.example deploy/example/.env.prod
```

Edit `deploy/example/.env.prod`:

```env
PULSEDECK_IMAGE=ghcr.io/artyum/pulsedeck:main-latest
DATABASE_URL=postgresql+psycopg://pulsedeck:CHANGE_ME@db-host:5432/pulsedeck
STORAGE_SECRET=CHANGE_ME_TO_LONG_RANDOM_SECRET
ENVIRONMENT=prod
APP_BASE_URL=https://pulsedeck.example.com
ALLOWED_HOSTS=pulsedeck.example.com
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=CHANGE_ME_Strong1!
```

Create data directories (paths are relative to `deploy/example/`):

```bash
mkdir -p deploy/data/uploads deploy/logs
```

Start:

```bash
docker compose --env-file deploy/example/.env.prod \
  -f deploy/example/docker-compose.prod.yml up -d
```

Volumes map `deploy/data/uploads` and `deploy/logs` into the container.

If you keep compose files in a separate `docker/` catalog (same pattern as [Lantern](https://github.com/artyum/lantern) or [OCR Machine](https://github.com/artyum/ocr-machine)), copy `deploy/example/docker-compose.prod.yml` and `.env.prod` there and adjust paths.

### Pre-built images (GHCR)

CI (lint + pytest) runs on pull requests to `main`. Images are built and pushed on every push to `main` and on `v*` tags. After a successful publish, GHCR versions, workflow runs, and Actions caches are trimmed to the 3 newest.

```
ghcr.io/artyum/pulsedeck:main-latest
ghcr.io/artyum/pulsedeck:latest
ghcr.io/artyum/pulsedeck:main
ghcr.io/artyum/pulsedeck:<short-sha>
ghcr.io/artyum/pulsedeck:vX.Y.Z
```

To make the package public: GitHub → **Packages** → **pulsedeck** → **Package settings** → **Change visibility**.

If the GitHub repository is named differently, use `ghcr.io/<owner>/<repo>:main-latest` instead.

## Development

### Requirements

- Docker with Compose v2
- PostgreSQL reachable from the host (connection string in `deploy/.env.dev`)
- Optional: Python 3.13+ and Node.js 22+ for linting outside Docker
- Optional: external Docker network `traefik-net` if you use the Traefik labels in dev compose

### Setup

```bash
cp deploy/example/.env.dev.example deploy/.env.dev
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
npm ci
```

Create the Traefik network if you need it:

```bash
docker network create traefik-net
```

Build frontend assets locally (optional; the Docker image builds them):

```bash
npm run build
```

### Dev workflow

The dev container mounts `app/`, `frontend/`, and `alembic/`. Restart after backend changes; run the CSS watcher for Tailwind.

| Script                | Description                                         |
| --------------------- | --------------------------------------------------- |
| `./build_app.sh`      | Build the dev image and start the container         |
| `./start_app.sh`      | Start the dev container (and CSS watcher if needed) |
| `./stop_app.sh`       | Stop the dev container and CSS watcher              |
| `./restart_app.sh`    | Restart the dev container                           |
| `./docker_logs.sh`    | Follow container logs                               |
| `./deploy/build.sh`   | Build dev image only                                |
| `./run_tests.sh`      | Run pytest (`.venv`)                                |
| `./run_lint_check.sh` | Run ruff, djLint, Prettier, stylelint, jscpd        |
| `./run_audit.sh`      | Run pip-audit, npm audit, and Trivy on local image  |
| `./update_npm.sh`     | Update npm dependencies                             |
| `./css_watcher.sh`    | Tailwind CSS watch (started by `start_app.sh`)      |

Typical flow:

```bash
./build_app.sh          # first run: build + start
# edit code under app/ and frontend/
./stop_app.sh           # when done
```

Dev compose file: [`deploy/docker-compose.dev.yml`](deploy/docker-compose.dev.yml).  
By default the app is exposed through Traefik at `pulsedeck.lan`; adjust labels or publish port `8000` if needed.

### Run without Docker

You still need PostgreSQL, Node.js (for CSS/JS build), and a configured `deploy/.env.dev` (or exported env vars).

```bash
export DATABASE_URL=postgresql+psycopg://pulsedeck:pulsedeck@127.0.0.1:5432/pulsedeck
export STORAGE_SECRET=dev-only-change-me
export ENVIRONMENT=dev
alembic upgrade head
python -m app.bootstrap
npm run build
uvicorn app.main:fastapi_app --reload
```

Run the mail worker in a second terminal:

```bash
python -m app.workers.mail
```

## API

| Method | Path          | Description  |
| ------ | ------------- | ------------ |
| `GET`  | `/api/health` | Health check |

OpenAPI docs are disabled in production builds.

## License

[MIT](LICENSE)

# Development

Day-to-day development uses Docker. The dev container mounts `app/`, `frontend/`, and `alembic/`. Restart after backend changes. Tailwind rebuilds through the CSS watcher.

## Requirements

- Docker with Compose v2
- PostgreSQL reachable from the host (`DATABASE_URL` in `deploy/.env.dev`)
- Optional: Python 3.13+ and Node.js 22+ to run lint on the host
- Optional: a Docker network named `traefik-net` if you use the Traefik labels in the dev compose file

## Setup

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

Build frontend assets on the host only when you want them outside the image:

```bash
npm run build
```

## Scripts

| Script                | Description                                             |
| --------------------- | ------------------------------------------------------- |
| `./build_app.sh`      | Build the dev image and start the container             |
| `./start_app.sh`      | Start the dev container (and the CSS watcher if needed) |
| `./stop_app.sh`       | Stop the dev container and the CSS watcher              |
| `./restart_app.sh`    | Restart the dev container                               |
| `./docker_logs.sh`    | Follow container logs                                   |
| `./deploy/build.sh`   | Build the dev image only                                |
| `./run_tests.sh`      | Run pytest with `.venv`                                 |
| `./run_lint_check.sh` | Run ruff, djLint, Prettier, stylelint, jscpd            |
| `./run_audit.sh`      | Run pip-audit, npm audit, and Trivy on the local image  |
| `./update_npm.sh`     | Update npm dependencies                                 |
| `./css_watcher.sh`    | Tailwind watch (also started by `start_app.sh`)         |

Typical flow:

```bash
./build_app.sh
# edit code under app/ and frontend/
./stop_app.sh
```

Compose file: [`deploy/docker-compose.dev.yml`](../deploy/docker-compose.dev.yml). By default the app is published through Traefik at `http://pulsedeck.lan/`. The dev env sets `UVICORN_HOST=0.0.0.0` so that hostname reaches the machine’s LAN address.

`start_app.sh` is enough when the image is already built. Edit `frontend/static/css/tailwind.css`; `app.css` is generated from it.

## Without Docker

You still need PostgreSQL, Node.js for the CSS and JS build, and `deploy/.env.dev` (or the same variables exported in the shell).

```bash
export DATABASE_URL=postgresql+psycopg://pulsedeck:pulsedeck@127.0.0.1:5432/pulsedeck
export STORAGE_SECRET=dev-only-change-me
export ENVIRONMENT=development
alembic upgrade head
python -m app.bootstrap
npm run build
uvicorn app.main:fastapi_app --reload
```

Run the mail worker in a second terminal:

```bash
python -m app.workers.mail
```

## Health

`GET /api/health` returns the process health check.

Previous: [Administration](admin.md) · Next: [Architecture](architecture.md)

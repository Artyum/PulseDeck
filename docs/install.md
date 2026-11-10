# Install

One organization, one deployment. Point `DATABASE_URL` at PostgreSQL, then start the published image.

## What you need

- Docker with Compose v2
- A PostgreSQL database the app can reach
- A public URL for links in email (`APP_BASE_URL`)

## Production (Docker Compose)

1. Copy the example env file:

   ```bash
   cp deploy/example/.env.prod.example deploy/example/.env.prod
   ```

2. Edit `deploy/example/.env.prod`. At minimum set:

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

3. Create data directories (paths are relative to `deploy/example/`):

   ```bash
   mkdir -p deploy/data/uploads deploy/logs
   ```

4. Start. Compose runs three services: `migrate` (database upgrade), `web`, and `worker` (email outbox).

   ```bash
   docker compose --env-file deploy/example/.env.prod \
     -f deploy/example/docker-compose.prod.yml up -d
   ```

5. Open `APP_BASE_URL` and sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`. That account is created on the first run only.

6. In **Administration → Settings → Mail**, set SMTP and send a test message when you want outbound mail. See [Configuration](configuration.md).

Uploads and logs are stored in `deploy/data/uploads` and `deploy/logs`.

If you keep compose files in a separate catalog, copy `deploy/example/docker-compose.prod.yml` and `.env.prod` there and adjust the volume paths.

## Images

CI publishes images on every push to `main` and on `v*` tags. Older GHCR versions are trimmed to the three newest.

```
ghcr.io/artyum/pulsedeck:main-latest
ghcr.io/artyum/pulsedeck:latest
ghcr.io/artyum/pulsedeck:main
ghcr.io/artyum/pulsedeck:<short-sha>
ghcr.io/artyum/pulsedeck:vX.Y.Z
```

If the GitHub repository name differs, use `ghcr.io/<owner>/<repo>:main-latest`.

To make the package public: GitHub → **Packages** → **pulsedeck** → **Package settings** → **Change visibility**.

## First steps after sign-in

1. Create a project with at least one staff member. Every project keeps at least one staff member.
2. Create users. New accounts get an activation link by email, or you can create them already active.
3. Add each person to the projects they should see, as **Client** or **Staff**.

Administrators can open every project. They still need a staff membership on a project to be assigned tickets and to receive ticket email. See [Roles](roles.md).

Previous: [README](../README.md) · Next: [Configuration](configuration.md)

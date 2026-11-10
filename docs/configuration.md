# Configuration

Settings come from the environment file on startup, and a few of them can be changed later in **Administration → Settings**. Portal settings saved in the UI override the values that were only a first-run seed (description length, reply length, reopen window).

Full templates: [`deploy/example/.env.dev.example`](../deploy/example/.env.dev.example), [`deploy/example/.env.prod.example`](../deploy/example/.env.prod.example).

## Required

| Variable         | Description                                                                                      |
| ---------------- | ------------------------------------------------------------------------------------------------ |
| `DATABASE_URL`   | PostgreSQL URL, for example `postgresql+psycopg://user:pass@host:5432/pulsedeck`                 |
| `STORAGE_SECRET` | Signs the session cookie. Use a long random value in production. Changing it signs everyone out. |
| `ENVIRONMENT`    | `development`, `preprod`, or `prod`                                                              |
| `APP_BASE_URL`   | Public URL used in email links (scheme and host, no path)                                        |
| `ALLOWED_HOSTS`  | Comma-separated hostnames the app will answer                                                    |

`ADMIN_EMAIL` and `ADMIN_PASSWORD` create the first administrator on an empty database. After that account exists, later starts keep the users already in the database.

## Mail and sign-in

| Variable                  | Default | Description                                                                  |
| ------------------------- | ------- | ---------------------------------------------------------------------------- |
| `SMTP_SERVER`             | —       | SMTP host. Set this to send outbound mail.                                   |
| `SMTP_PORT`               | `587`   | SMTP port                                                                    |
| `SMTP_USER` / `SMTP_PASS` | —       | SMTP credentials                                                             |
| `EMAIL_FROM`              | —       | From address                                                                 |
| `MFA_ENABLED`             | `false` | After the password, email a 6-digit code. Requires SMTP outside development. |
| `MFA_TTL`                 | `30d`   | How long “don’t ask on this device” lasts, from 1 to 365 days                |
| `SESSION_MAX_AGE_SECONDS` | `28800` | Session length. Activity extends it.                                         |

SMTP, the from-address, and a test message can also be set in **Administration → Settings → Mail**. The code is valid for 10 minutes. A wrong code can be tried 5 times.

## Tickets and uploads

These environment values seed the database. Change them afterwards in **Administration → Settings**.

| Variable                     | Default  | Description                                                          |
| ---------------------------- | -------- | -------------------------------------------------------------------- |
| `TICKET_REOPEN_DAYS`         | `7`      | Days after close when the reporter may reopen. `0` means staff only. |
| `TICKET_DESCRIPTION_MAX_LEN` | `100000` | Description length, including Markdown                               |
| `TICKET_REPLY_MAX_LEN`       | `100000` | Comment length, including Markdown                                   |

Attachment limits (count, image size, other file size) live in the same settings screen. Allowed images: JPG, PNG, WebP, GIF. Allowed other files: PDF, DOCX, XLSX, PPTX, TXT, CSV, LOG, JSON, XML, ZIP, RAR, 7Z.

## Process

| Variable                | Default     | Description                                                                          |
| ----------------------- | ----------- | ------------------------------------------------------------------------------------ |
| `UVICORN_HOST`          | `127.0.0.1` | Bind address inside the container. Use `0.0.0.0` when a proxy reaches the container. |
| `UVICORN_PORT`          | `8000`      | HTTP port                                                                            |
| `UVICORN_WORKERS`       | `1`         | Worker processes                                                                     |
| `UVICORN_PROXY_HEADERS` | `false`     | Turn on behind a reverse proxy                                                       |

Password length, rate limits, upload directories, and log settings are in the example env files.

Previous: [Install](install.md) · Next: [Roles](roles.md)

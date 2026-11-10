# Architecture

PulseDeck is a server-rendered site. FastAPI returns HTML (Jinja), HTMX swaps fragments, and PostgreSQL holds the data. There is no public JSON API. OpenAPI, Swagger, and ReDoc are off. The only machine endpoint is `GET /api/health`.

## Processes

Production Compose runs three services against one database:

| Service   | Process                         | Role                                  |
| --------- | ------------------------------- | ------------------------------------- |
| `migrate` | `alembic upgrade head`          | Schema, once per start, then it exits |
| `web`     | Uvicorn, `app.main:fastapi_app` | HTTP                                  |
| `worker`  | `python -m app.workers.mail`    | Sends rows from `email_outbox`        |

The web process never talks to SMTP for ticket mail. It inserts a row. If the worker is down, the UI still succeeds and the message waits.

## Identifiers

Every table uses a bigint primary key. Nothing in a URL is that id.

A project has a `key` of 1–5 characters `A–Z` / `0–9`. A ticket has `number`, allocated per project from 1. Routes are `/p/{key}` and `/t/{key}-{number}`. The key is stored uppercase. Renaming the key or the project name does not write a redirect. Old links 404.

`key` and `number` are for routes and labels. Authorization uses the integer ids.

## Request path

Middleware order, outer first:

1. `SessionMiddleware` — cookie `pulsedeck_session`, signed with `STORAGE_SECRET`, `SameSite=Lax`. `https_only` is on when `ENVIRONMENT` is `preprod` or `prod`.
2. `SessionSlidingMiddleware` — activity extends the session up to `SESSION_MAX_AGE_SECONDS`.
3. `CSRFProtectMiddleware` — `POST` / `PUT` / `PATCH` / `DELETE` need `X-CSRF-Token` or a form field. Exempt: login, forgot-password, activate, and the unsubscribe confirm. Those have no session yet, or only a one-time link.
4. `SlowAPIMiddleware` — per-route limits (login, forgot-password, uploads, and similar).
5. `TrustedHostMiddleware` — `ALLOWED_HOSTS`. Development also allows `testserver`, `localhost`, `127.0.0.1`, and `pulsedeck.lan`.
6. Security headers (CSP, `X-Content-Type-Options`, frame denial; HSTS when enabled).

The session stores `user_id` and `auth_epoch`. On each request the epoch is compared with `users.auth_epoch`. A mismatch clears the cookie. The epoch moves when a password is set or changed, an administrator sets the email or the password, the user confirms an email change, or the account is blocked. Magic links (activation, reset, email confirm) store only a hash. Using one, or replacing the password, marks the user’s unused links as used.

Passwords are bcrypt with 12 rounds. The configured maximum length is 72 bytes, which is the bcrypt input limit.

`MFA_ENABLED` adds a second step: a 6-digit code, 10 minutes, 5 attempts, delivered through the same outbox at auth priority. Trust is a separate cookie, not the session, and `MFA_TTL` is how long that browser may skip the code.

## Authorization

Two axes, both checked on the server:

- `users.role`: `USER` or `ADMIN`. An administrator can open every project, edit any ticket, and soft-delete tickets and comments.
- `project_members.role`: `CLIENT` or `STAFF` for that project. Staff can assign, change workflow fields, manage tags and participants, and write internal notes. A project must keep one active staff member.

An administrator who is not a project member can read the project. Assignment and ticket email still require a staff membership, because the assignee must be staff on that project.

Ticket delete sets `deleted_at`. The row, comments, and files stay. Non-admins no longer see it.

The reporter may edit the title and description until `author_edits_locked_at` is set. The first comment or the first assignment sets it. A comment locks the ticket in the same transaction that inserts it, so the author cannot edit that comment afterwards. Administrators bypass the lock.

## Mail worker

`claim_next` takes the oldest pending row with `FOR UPDATE SKIP LOCKED`. Auth mail (`priority = auth`) is ordered before ticket mail. Ticket mail is also held when the process has already sent `MAIL_MAX_PER_HOUR` ticket messages in the last hour (default 300). Auth mail is not counted in that cap.

A claimed row is marked `sending` before SMTP. On startup, leftover `sending` rows go back to `pending`. A failed send is retried up to `MAIL_MAX_ATTEMPTS` (default 5) with backoff `min(300, 2^attempts)` seconds. Pending rows older than `MAIL_MAX_AGE_DAYS` (default 7) are marked `failed` with `last_error = expired`. After a successful ticket send the loop sleeps `MAIL_MIN_INTERVAL_MS` (default 3000).

## Uploads

The extension whitelist is enforced, then the bytes. Images (including GIF) are decoded with Pillow and written back as JPEG, quality 90, so the stored file is not the upload. An image may not exceed 20 million pixels or 4000 px on a side. Other types must match a magic-byte prefix (PDF, ZIP-based Office files, RAR, 7z). The path on disk is `{uuid}_{sha256[:12]}.ext` under the upload directory. The original name is kept only as a display label, with the path stripped.

## Interface language

Copy lives in `app/locales/en.yml` and `app/locales/pl.yml` and is read with `t()`. English is the default. `users.ui_lang`, the date format, and the time zone are columns. Theme, gradient, density, and font size are `localStorage` in the browser.

Schema changes go through Alembic only. The running app does not create tables.

Next: [Development](development.md) · [Configuration](configuration.md)

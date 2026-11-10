# Architecture

PulseDeck is a server-rendered site. FastAPI returns HTML (Jinja), HTMX swaps fragments, and PostgreSQL holds the data. The machine endpoint is `GET /api/health`.

## Processes

Production Compose runs three services against one database:

| Service   | Process                         | Role                                  |
| --------- | ------------------------------- | ------------------------------------- |
| `migrate` | `alembic upgrade head`          | Schema, once per start, then it exits |
| `web`     | Uvicorn, `app.main:fastapi_app` | HTTP                                  |
| `worker`  | `python -m app.workers.mail`    | Sends rows from `email_outbox`        |

The web process inserts a row into `email_outbox`. The worker sends it over SMTP. While the worker is stopped, the UI still records the message and it waits in the queue.

## Identifiers

Every table uses a bigint primary key. URLs use the project `key` and the ticket `number`.

A project has a `key` of 1–5 characters `A–Z` / `0–9`. A ticket has `number`, allocated per project from 1. Routes are `/p/{key}` and `/t/{key}-{number}`. The key is stored uppercase. The live address is the current key.

`key` and `number` are for routes and labels. Authorization uses the integer ids.

## Request path

Middleware order, outer first:

1. `SessionMiddleware` — cookie `pulsedeck_session`, signed with `STORAGE_SECRET`, `SameSite=Lax`. `https_only` is on when `ENVIRONMENT` is `preprod` or `prod`.
2. `SessionSlidingMiddleware` — activity extends the session up to `SESSION_MAX_AGE_SECONDS`.
3. `CSRFProtectMiddleware` — `POST` / `PUT` / `PATCH` / `DELETE` need `X-CSRF-Token` or a form field. Login, forgot-password, activate, and the unsubscribe confirm are exempt (they run before a session exists, or from a one-time link).
4. `SlowAPIMiddleware` — per-route limits (login, forgot-password, uploads, and similar).
5. `TrustedHostMiddleware` — `ALLOWED_HOSTS`. Development also allows `testserver`, `localhost`, `127.0.0.1`, and `pulsedeck.lan`.
6. Security headers (CSP, `X-Content-Type-Options`, frame denial; HSTS when enabled).

The session stores `user_id` and `auth_epoch`. On each request the epoch is compared with `users.auth_epoch`. A mismatch clears the cookie. The epoch moves when a password is set or changed, an administrator sets the email or the password, the user confirms an email change, or the account is blocked. Magic links (activation, reset, email confirm) store only a hash. Using one, or replacing the password, marks the user’s unused links as used.

Passwords are bcrypt with 12 rounds. The configured maximum length is 72 bytes, which is the bcrypt input limit.

`MFA_ENABLED` adds a second step: a 6-digit code, 10 minutes, 5 attempts, delivered through the same outbox at auth priority. Device trust is a separate cookie. `MFA_TTL` is how long that browser may skip the code.

## Authorization

Two axes, both checked on the server:

- `users.role`: `USER` or `ADMIN`. An administrator can open every project, edit any ticket, and soft-delete tickets and comments.
- `project_members.role`: `CLIENT` or `STAFF` for that project. Staff can assign, change workflow fields, manage tags and participants, and write internal notes. A project must keep one active staff member.

Administrators can read every project. Assignment and ticket email use a staff membership on that project; the assignee is always staff there.

Ticket delete sets `deleted_at`. The row, comments, and files stay. Administrators still see the ticket.

The reporter may edit the title and description until `author_edits_locked_at` is set. The first comment or the first assignment sets it, in the same transaction. Administrators can still edit after the lock.

## Mail worker

`claim_next` takes the oldest pending row with `FOR UPDATE SKIP LOCKED`. Auth mail (`priority = auth`) is ordered before ticket mail. Ticket mail waits when the process has already sent `MAIL_MAX_PER_HOUR` ticket messages in the last hour (default 300). Auth mail uses its own path, outside that cap.

A claimed row is marked `sending` before SMTP. On startup, leftover `sending` rows go back to `pending`. A failed send is retried up to `MAIL_MAX_ATTEMPTS` (default 5) with backoff `min(300, 2^attempts)` seconds. Pending rows older than `MAIL_MAX_AGE_DAYS` (default 7) are marked `failed` with `last_error = expired`. After a successful ticket send the loop sleeps `MAIL_MIN_INTERVAL_MS` (default 3000).

## Uploads

The extension whitelist is enforced, then the bytes. Images (including GIF) are decoded with Pillow and written back as JPEG, quality 90. Images may be up to 20 million pixels and 4000 px on a side. Other types must match a magic-byte prefix (PDF, ZIP-based Office files, RAR, 7z). The path on disk is `{uuid}_{sha256[:12]}.ext` under the upload directory. The original name is kept as a display label, with the path stripped.

## Interface language

Copy lives in `app/locales/en.yml` and `app/locales/pl.yml` and is read with `t()`. English is the default. `users.ui_lang`, the date format, and the time zone are columns. Theme, gradient, density, and font size are `localStorage` in the browser.

Schema changes go through Alembic.

Previous: [Development](development.md) · Next: [README](../README.md)

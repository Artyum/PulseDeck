# PulseDeck

A self-hosted support desk for one team and its clients. Projects, tickets, comments, email, and a bilingual UI — FastAPI and PostgreSQL.

Staff work in a portal. Clients see only their projects. There is no public sign-up and no second organization inside the same deployment.

## Guides

|                                                 |                                                  |
| ----------------------------------------------- | ------------------------------------------------ |
| [Install](docs/install.md)                      | Docker Compose, GHCR image, first sign-in        |
| [Configuration](docs/configuration.md)          | Environment variables, SMTP, MFA                 |
| [Roles](docs/roles.md)                          | Administrator, staff, client                     |
| [Portal](docs/portal.md)                        | Project list, views, filters, new ticket         |
| [Tickets](docs/tickets.md)                      | Status, people, tags, attachments, history       |
| [Comments and email](docs/comments-and-mail.md) | Replies, internal notes, notifications           |
| [Profile](docs/profile.md)                      | Language, theme, password, notification switches |
| [Administration](docs/admin.md)                 | Users, projects, portal settings, statistics     |
| [Development](docs/development.md)              | Local Docker workflow, tests, lint               |
| [Architecture](docs/architecture.md)            | Processes, sessions, mail queue, uploads         |

## What it does

- Ticket portal with readable addresses: `/p/{key}`, `/t/{key}-{number}`
- Types, statuses, priorities, tags, assignee, participants
- Markdown comments and internal notes for staff
- Email from an outbox worker (SMTP), with unsubscribe links
- Optional email sign-in code (`MFA_ENABLED`)
- English and Polish
- Light and dark theme pairs, spacing, and font size
- PWA basics (service worker, offline page)
- Docker image on GHCR

## What it does not do

- No multi-tenant SaaS — one deployment, one organization
- No PostgreSQL container in the production compose file — bring your own database
- No LDAP or OAuth — email and password, plus an optional email code
- No anonymous reply from an email link — the message opens the ticket after sign-in

## First run

1. Copy [`deploy/example/.env.prod.example`](deploy/example/.env.prod.example) and set `DATABASE_URL`, `STORAGE_SECRET`, `APP_BASE_URL`, and the bootstrap admin.
2. Start Compose as described in [Install](docs/install.md).
3. Sign in, then set SMTP under **Administration → Settings → Mail** if you want mail.

## License

[MIT](LICENSE)

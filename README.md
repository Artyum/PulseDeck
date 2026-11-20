# PulseDeck

PulseDeck is a support desk you host yourself, for one team and the people that team helps. Staff work in a portal. Clients see only the projects they belong to. An administrator creates the accounts. One installation serves one organization.

Each ticket has a type, a status, a priority, tags, someone assigned to it, and people who follow it. Replies are written in Markdown. Staff can leave a note that clients never see. When mail is set up, people hear about new tickets and replies, and a message includes a link to turn that kind of mail off. Sign-in can ask for a short code by email. The interface is in eighteen languages. Each colour theme has a light and a dark version, and you can change spacing and type size. If the network drops, a small offline page is there.

The application, and the translations of its interface, were made with the help of AI. English is the source text. The other languages were generated from it, so a phrase may still sound a little stiff.

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

## First run

1. Copy [`deploy/example/.env.prod.example`](deploy/example/.env.prod.example) and set `DATABASE_URL`, `STORAGE_SECRET`, `APP_BASE_URL`, and the bootstrap admin.
2. Start Compose as described in [Install](docs/install.md).
3. Sign in, then set SMTP under **Administration → Settings → Mail** if you want mail.

## License

[MIT](LICENSE)

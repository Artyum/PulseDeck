# Portal

The portal is the ticket list. The address of a project is `/p/{key}`, where `key` is the short code chosen in administration (1–5 letters or digits).

The portal lists the projects you belong to. An administrator adds you to a project.

## Switching project

The header lists the projects you can open. Administrators see every project. Everyone else sees projects they are a member of.

## Views

The view tabs change with your project role.

| View           | Who      | Shows                               |
| -------------- | -------- | ----------------------------------- |
| All            | everyone | Every ticket in the project         |
| Open           | everyone | New, In progress, and With reporter |
| Closed         | everyone | Done                                |
| To handle      | staff    | New and In progress                 |
| Unassigned     | staff    | Tickets with no assignee            |
| Awaiting reply | clients  | With reporter                       |

## Filters

- Search matches title, ticket number, or reporter.
- Type, status, priority, and tag narrow the list. Tag choices are the tags already used in that project.
- **Only mine** keeps tickets you reported, are assigned to, or watch.
- Sort by last activity, creation date, or priority.

The header lists **active** projects. Enable a project in Administration to show it in the portal again. Its tickets stay in the database.

## Creating a ticket

**Create ticket** asks for a title, type, priority, and description. The description is Markdown. The new ticket starts as **New**, you are the reporter, and its address is `/t/{key}-{number}` (`number` starts at 1 inside that project).

Types: Bug, Question, Change, New feature. Priorities: Low, Normal, High.

Previous: [Roles](roles.md) · Next: [Tickets](tickets.md)

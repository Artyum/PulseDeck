# Roles

There is no public sign-up. An administrator creates every account. Two switches decide what a person can do: the account role, and the role on each project.

## Account role

| Role              | What they can do                                                                                         |
| ----------------- | -------------------------------------------------------------------------------------------------------- |
| **User**          | Only the projects they belong to                                                                         |
| **Administrator** | Open every project, use Administration, edit any ticket, delete tickets and comments, see hidden tickets |

An administrator who is not a member of a project can still open it. To be assigned a ticket, or to receive ticket email, add them to that project as **Staff**. The profile screen says the same thing.

## Project role

| Role       | What they can do                                                                                                                    |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **Client** | See the project’s tickets, create tickets, follow tickets they report or are added to                                               |
| **Staff**  | Everything a client can do, plus assign work, change type, status, and priority, manage tags and participants, write internal notes |

A project always keeps at least one staff member.

## Who sees a ticket

Members of the project see its tickets. Clients do not see internal notes.

On a single ticket:

- **Reporter** is the person the ticket is for. Staff can change the reporter.
- **Assignee** is a staff member responsible for it. Assigning someone moves a **New** ticket to **In progress**.
- **Participants** watch the ticket and get reply email. The reporter is involved without being listed again. The assignee is not also stored as a participant.

## Signing in

Sign-in is email and password. A blocked account cannot sign in. An account that has not been activated is told to use the email link or **Forgot your password**.

When `MFA_ENABLED` is on, the next step is a 6-digit code sent by email, unless this browser was trusted. Trust lasts for `MFA_TTL`. See [Configuration](configuration.md).

Next: [Portal](portal.md) · [Administration](admin.md)

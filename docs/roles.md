# Roles

An administrator creates every account. Two switches decide what a person can do: the account role, and the role on each project.

## Account role

| Role              | What they can do                                                                                         |
| ----------------- | -------------------------------------------------------------------------------------------------------- |
| **User**          | Only the projects they belong to                                                                         |
| **Administrator** | Open every project, use Administration, edit any ticket, delete tickets and comments, see hidden tickets |

Administrators can open every project. Add them to a project as **Staff** so they can be assigned tickets and receive ticket email. The profile screen says the same thing.

## Project role

| Role       | What they can do                                                                                                                    |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **Client** | See the project’s tickets, create tickets, follow tickets they report or are added to                                               |
| **Staff**  | Everything a client can do, plus assign work, change type, status, and priority, manage tags and participants, write internal notes |

A project always keeps at least one staff member.

## Who sees a ticket

Members of the project see its tickets. Internal notes are visible to staff.

On a single ticket:

- **Reporter** is the person the ticket is for. Staff can change the reporter.
- **Assignee** is a staff member responsible for it. Assigning someone moves a **New** ticket to **In progress**.
- **Participants** watch the ticket and get reply email. The reporter and the assignee already receive those updates.

## Signing in

Sign-in is email and password. Active, activated accounts can sign in. Pending accounts use the activation link or **Forgot your password**. Unblock a blocked account to restore sign-in.

When `MFA_ENABLED` is on, the next step is a 6-digit code sent by email, unless this browser was trusted. Trust lasts for `MFA_TTL`. See [Configuration](configuration.md).

Previous: [Configuration](configuration.md) · Next: [Portal](portal.md)

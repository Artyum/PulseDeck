# Administration

**Administration** is in the user menu for administrators only.

## Statistics

Counts for projects, users, open tickets, messages, accounts waiting for activation, and email sent. Pick a project to see its members, tickets, status mix, and type mix. The activity table lists who created tickets and when they last signed in.

## Users

Create a user with a name, email, account role (**User** or **Administrator**), and at least one project.

- **Create and send activation link** — the person sets a password from the email.
- **Create without activation** — the account can sign in once a password is set for it.

The list filters by role, project, status (active, blocked, pending activation), and text (name, email, phone).

From a user you can edit the account, resend the activation link, or block and unblock. A blocked person cannot sign in. Pending means the activation link has not been used yet.

## Projects

A project has a **name** (unique, case-insensitive) and a **key** of 1–5 characters `A–Z` or `0–9` (unique). The key is part of every ticket address: `/p/HELP`, `/t/HELP-3`. Changing the key or the name does not redirect old addresses. Old links stop working.

Each new project needs an initial staff member.

On the project page:

- **Open in portal** jumps to the ticket list.
- **Disable** hides it from day-to-day use. **Enable** brings it back. Disabled projects are a separate filter on the project list.
- **Notify clients about team-created tickets** — off by default. Turn it on when clients should get email about tickets the team opens.
- **Members** — add a person as **Client** or **Staff**, or change that role. The last staff member cannot be removed or demoted.
- **Tags** — tags already used in the project. Deleting one removes it from the project.

## Settings

Saved here, not in the env file (the env file only supplies the first values):

| Section     | What it controls                                                                                                                        |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Tickets     | Reopen window, description length, reply length, how long activation and password-reset links last, how long an email-change link lasts |
| Attachments | How many files on one ticket or comment, and the size cap for images and for other files                                                |
| Mail        | SMTP host, port, security (none, STARTTLS, SSL/TLS), username, password, from-address, and a test message                               |

Leave the SMTP password blank to keep the one already stored. Save before sending the test. The test uses the saved settings.

See [Configuration](configuration.md) for the environment variables that still have to be set outside the UI, and [Comments and email](comments-and-mail.md) for who receives which message.

Next: [Install](install.md)

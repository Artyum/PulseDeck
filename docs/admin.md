# Administration

**Administration** is in the user menu for administrators only.

## Statistics

Counts for projects, users, open tickets, messages, accounts waiting for activation, and email sent. Pick a project to see its members, tickets, status mix, and type mix. The activity table lists who created tickets and when they last signed in.

## Users

Create a user with a name, email, account role (**User** or **Administrator**), and at least one project. You can send an activation link so the person sets their own password from the email, or create the account without that mail and set a password for them yourself.

The list filters by role, project, status (active, blocked, pending activation), and text (name, email, phone).

From a user you can edit the account, resend the activation link, or block and unblock. Blocking ends sign-in until you unblock. Pending means the activation link is still unused.

## Projects

A project has a **name** (unique, case-insensitive) and a short **key** of 1–5 letters or digits (unique). The key is what people see on tickets, as in HELP-3. If you change the name or the key, old links stop working.

Each new project needs an initial staff member.

**Open in portal** jumps to the ticket list. **Disable** hides the project from day-to-day use, and **Enable** brings it back. Disabled projects stay on the project list behind their own filter. **Notify clients about team-created tickets** is off by default. Turn it on when clients should get email about tickets the team opens. Under **Members** you add a person as **Client** or **Staff**, or change that role. A project always keeps at least one staff member. **Tags** lists the tags already used in the project. Deleting one removes it from the project.

## Settings

These values live in portal settings. The env file seeds them on first run:

| Section     | What it controls                                                                                                                        |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Tickets     | Reopen window, description length, reply length, how long activation and password-reset links last, how long an email-change link lasts |
| Attachments | How many files on one ticket or comment, and the size cap for images and for other files                                                |
| Mail        | SMTP host, port, security (none, STARTTLS, SSL/TLS), username, password, from-address, and a test message                               |

Leave the SMTP password blank to keep the one already stored. Save before sending the test. The test uses the saved settings.

See [Configuration](configuration.md) for environment variables, and [Comments and email](comments-and-mail.md) for who receives which message.

Previous: [Profile](profile.md) · Next: [Development](development.md)

# Comments and email

Replies are Markdown. The editor has headings, lists, links, code, quotes, a divider, and dictation where the browser allows a microphone. You can quote selected text from an earlier message.

The thread can be read oldest-first or newest-first.

## Who can reply

Comments are allowed on an open ticket for:

- staff of the project and administrators
- the reporter
- a participant

Other project members can read the ticket. Add them as participants to give them a reply box.

A comment locks the ticket as soon as it is saved. After that, administrators can edit comments, the title, and the description. Only administrators can delete a comment. See [Tickets](tickets.md).

## Internal notes

Staff can mark a reply as an **internal note**. Internal notes are visible to staff, including in history. Public replies can move the ticket to **With reporter**.

## What email is sent

Mail is sent only when SMTP is configured. Each message includes a link to the ticket in the portal. You need to be signed in to read or reply.

| Message                          | Who receives it                                                                                                 |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| New ticket                       | Staff on the project, if they allow “New tickets”                                                               |
| New ticket created by staff      | Clients only when the project option **Notify clients about team-created tickets** is on. It is off by default. |
| New comment                      | People involved in the ticket who allow “Replies”. Internal notes stay inside the staff audience.               |
| Status, type, or priority change | People involved in the ticket who allow that switch                                                             |
| Assignment                       | The new assignee                                                                                                |

The reporter, assignee, and participants count as involved. Profile switches apply to every ticket. See [Profile](profile.md).

Every notification has two one-shot links:

- **Unsubscribe** turns off that kind of notification on the account (replies, new tickets, or status changes).
- **Stop watching** removes you from that one ticket’s participants.

Both links ask for confirmation and expire if they are invalid.

Activation, password reset, and email-change messages use the same outbox. Their lifetime is set under **Administration → Settings → Tickets** (days for activation and reset, minutes for an email change).

The `worker` service delivers the queue. If mail piles up, check that the worker is running and that a test message from **Settings → Mail** succeeds.

Previous: [Tickets](tickets.md) · Next: [Profile](profile.md)

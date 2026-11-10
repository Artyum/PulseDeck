# Tickets

A ticket is one request. The label in the interface is `{key}-{number}`, for example `HELP-12`, and the address is `/t/HELP-12`.

## Status

| Status            | Meaning                              |
| ----------------- | ------------------------------------ |
| **New**           | Nobody is working on it yet          |
| **In progress**   | The team is working on it            |
| **With reporter** | The team is waiting for the reporter |
| **Done**          | Closed                               |

Staff set type, status, and priority from the ticket. A public reply can set the status at the same time: staff replies default toward **With reporter**, a client reply defaults toward **In progress**. Either side can also mark it **Done** when they are allowed to close it (staff, or the reporter).

A public reply can change the status. An internal note keeps the current status.

## Reopening

Staff can reopen a closed ticket at any time. The reporter can reopen it for the number of days in **Administration → Settings → Tickets** (default 7). `0` limits reopening to staff. Reopen a ticket to add comments.

## People

- **Assign me** and the assignee field are for staff. The assignee must be staff on this project.
- **Participants** are people who watch the ticket. Staff add or remove them. **Stop watching** removes you.
- Removing a watcher stops reply email for this ticket only. Account-wide notification switches are in the profile.

## Tags

Staff add and remove tags on the ticket. The project settings page lists tags used in that project and can delete a tag there.

## Description and title

The reporter can edit the title and description until the ticket is locked. It locks when someone comments, or when an assignee is set. After that, only an administrator can edit them.

## Attachments

Files can be added on the ticket or on a comment: pick, drop, or paste. Limits and allowed types are in [Configuration](configuration.md). Images open in a preview.

## History

**History** lists changes: title, description, status, type, priority, reporter, assignee, participants, tags, attachments, and deleted comments. Staff also see events for internal notes.

## Deleting

Only an administrator can delete a ticket or a comment. A deleted ticket is hidden from everyone else. Administrators still see it, with a banner, and it stays out of the normal list as a deleted item.

Previous: [Portal](portal.md) · Next: [Comments and email](comments-and-mail.md)

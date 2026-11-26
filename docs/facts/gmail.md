# Gmail and other mailboxes (reading through IMAP)

Checked 2026-11-22. https://support.google.com/mail

- VERIFIED: 2 step verification must be on, then make an app password at myaccount.google.com/apppasswords.
- IMAP host imap.gmail.com, port 993 (SSL).
- Less secure app access ended on 2024-09-30 (third party source).
- In this project: the IMAP adapter only reads. It was tested against a local mock mail server and never run against a real mailbox. Slatehire never sends email.

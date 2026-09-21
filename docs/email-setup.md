# Email setup (note invitations)

Notely sends one kind of email: the invitation when you share a note with someone by
address. Delivery goes through plain SMTP, so any transactional provider works:

| Provider | SMTP_HOST | SMTP_PORT | Username / password |
|---|---|---|---|
| Amazon SES | `email-smtp.<region>.amazonaws.com` | 587 | SMTP credentials from the SES console |
| Postmark | `smtp.postmarkapp.com` | 587 | server API token as both |
| SendGrid | `smtp.sendgrid.net` | 587 | `apikey` / your API key |
| Resend | `smtp.resend.com` | 587 | `resend` / your API key |
| Mailgun | `smtp.mailgun.org` | 587 | SMTP user / SMTP password |
| Gmail (personal) | `smtp.gmail.com` | 587 | address / **app password** |

Put the values in `apps/api/.env`:

```
SMTP_HOST=smtp.postmarkapp.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM=notely@yourdomain.com     # a sender your provider has verified
SMTP_FROM_NAME=Notely AI
SMTP_STARTTLS=true                  # 587; set SMTP_SSL=true and SMTP_PORT=465 for implicit TLS
INVITATION_TTL_DAYS=7
```

`FRONTEND_ORIGIN` must be the public URL of the web app — it is the base of the link in the
email (`{FRONTEND_ORIGIN}/invite/<token>`).

## What happens when it is not configured

The invitation is still created and shows up in the Share dialog as *Invited — waiting for
them to open the email*, but the API answers with `delivery.sent = false` and the reason, and
the UI shows **Unable to send invitation** with that reason. Nothing pretends the message went
out. The invited person still gets access if they sign up with that address, and the owner can
**Resend** once SMTP is configured.

## Lifecycle

- One pending invitation per address per note. Inviting the same address again returns
  `409 INVITE_ALREADY_SENT`; **Resend** issues a fresh link and expiry.
- Links expire after `INVITATION_TTL_DAYS`; an expired link shows *Invitation expired* and the
  owner can resend.
- Accepting requires being signed in with the invited address (`403 INVITE_WRONG_ACCOUNT`
  otherwise); the link is single-use. Signing up with the invited address accepts implicitly.

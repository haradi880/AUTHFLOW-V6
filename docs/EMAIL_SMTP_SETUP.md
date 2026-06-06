# Email Setup

HaradiBots supports SMTP and HTTPS email APIs. On Render, HTTPS APIs are usually more reliable than SMTP.

## Recommended On Render: Resend

SMTP can time out on Render even when the app is configured correctly. Resend uses HTTPS instead of SMTP ports.

Set these Render environment variables:

```env
EMAIL_BACKEND=resend
EMAIL_DELIVERY_ORDER=resend
RESEND_API_KEY=re_your_key_here
RESEND_FROM=HaradiBots <your-verified-sender@example.com>
MAIL_DEFAULT_SENDER=your-verified-sender@example.com
```

`RESEND_FROM` must be a sender/domain verified in Resend.

## Important Render Limitation

Render Free web services commonly block outbound SMTP ports `25`, `465`, and `587`.
Docker does not bypass this because the block is outside the container.

To use SMTP on Render without upgrading, use an SMTP provider that documents support for port `2525`.

## Gmail SMTP

Use a Gmail app password, not your normal Gmail password.

Required Google account setup:

1. Enable 2-Step Verification.
2. Create an App Password for this app.
3. Put the 16-character app password in `MAIL_PASSWORD`.

Environment:

```env
EMAIL_BACKEND=smtp
EMAIL_DELIVERY_ORDER=smtp
EMAIL_FILE_FALLBACK=false

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_FORCE_IPV4=true
MAIL_USERNAME=your-address@gmail.com
MAIL_PASSWORD=your-16-character-app-password
MAIL_DEFAULT_SENDER=your-address@gmail.com
MAIL_SENDER_NAME=HaradiBots
```

Test SMTP directly:

```powershell
flask --app app:create_app email-check --backend smtp --to your-address@gmail.com
```

## Other SMTP Providers

For Brevo, SMTP2GO, Mailgun, Zoho, Hostinger, or custom mail hosting, use the server, port, TLS/SSL mode, username, password, and sender address from that provider.

Common modes:

```env
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USE_SSL=false
```

or:

```env
MAIL_PORT=465
MAIL_USE_TLS=false
MAIL_USE_SSL=true
```

Render-friendly port `2525`:

```env
MAIL_SERVER=your-provider-smtp-host
MAIL_PORT=2525
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_FORCE_IPV4=true
```

Use this only if your SMTP provider documents port `2525`. Gmail SMTP usually uses `587` with TLS or `465` with SSL, not `2525`.

## Production Recommendation

Use exactly one primary delivery path in production:

```env
EMAIL_BACKEND=smtp
EMAIL_DELIVERY_ORDER=smtp
EMAIL_FILE_FALLBACK=false
```

File fallback is only for local development. It writes `.eml` files and does not deliver real OTP emails.

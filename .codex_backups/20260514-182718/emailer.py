"""
Email Helper - Sends emails for OTP verification and notifications.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app


def send_email(to_email, subject, body):
    """
    Send an email using SMTP.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Plain text email body
    """
    try:
        # Get email settings from Flask config
        sender = current_app.config['MAIL_DEFAULT_SENDER']
        username = current_app.config['MAIL_USERNAME']
        password = current_app.config['MAIL_PASSWORD']
        if not username or not password:
            current_app.logger.info("Email delivery skipped; SMTP credentials are not configured. To=%s Subject=%s Body=%s", to_email, subject, body)
            return False
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = f"AuthFlow <{sender}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Connect to SMTP server and send
        server = smtplib.SMTP(current_app.config['MAIL_SERVER'], 
                              current_app.config['MAIL_PORT'])
        server.starttls()
        server.login(username, password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        current_app.logger.warning("Failed to send email to %s: %s", to_email, e)
        return False


def send_otp_email(email, otp):
    """Send OTP verification code to user's email."""
    subject = "Your Verification Code - AuthFlow"
    body = f"""
Hello!

Your verification code is: {otp}

This code will expire in 5 minutes.

If you didn't request this code, please ignore this email.

Best regards,
AuthFlow Team
"""
    return send_email(email, subject, body)


def send_welcome_email(email, username):
    """Send welcome email to new users."""
    subject = "Welcome to AuthFlow!"
    body = f"""
Hello {username}!

Welcome to AuthFlow - the developer blogging platform.

You can now:
- Write and publish blog posts
- Share your projects
- Follow other developers
- Build your portfolio

Get started by writing your first blog post!

Best regards,
AuthFlow Team
"""
    return send_email(email, subject, body)

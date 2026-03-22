"""
email_service.py — Django email sending.
FIX: SSL certificate verification disabled for Python 3.14 compatibility.
Uses EMAIL_USE_SSL=True on port 465 instead of TLS on 587.
"""
import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.conf import settings
from apps.db import get_cursor, close_connection


def send_email(to, subject, body, html=None):
    """Send email using raw smtplib with SSL verification disabled."""
    try:
        # Create unverified SSL context — fixes Python 3.14 certificate error
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode    = ssl.CERT_NONE

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = settings.DEFAULT_FROM_EMAIL
        msg["To"]      = to

        msg.attach(MIMEText(body, "plain"))
        if html:
            msg.attach(MIMEText(html, "html"))

        # Use SMTP_SSL on port 465 — more reliable than STARTTLS on 587
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl_context) as server:
            server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            server.sendmail(settings.EMAIL_HOST_USER, [to], msg.as_string())

        success = True
    except Exception as e:
        print(f"Email send error: {e}")
        success = False

    # Log to DB
    try:
        cursor, conn = get_cursor()
        cursor.execute(
            "INSERT INTO email_logs(recipient, subject) VALUES(%s, %s)",
            (to, subject)
        )
        conn.commit()
        close_connection(cursor, conn)
    except Exception as e:
        print(f"[email_logs] Failed to log: {e}")

    return success


def send_event_approval_email(to, user_name, event_title, approved_by):
    send_email(
        to,
        f"Event Approved: {event_title}",
        f"""Hello {user_name},

Great news! Your event "{event_title}" has been approved by {approved_by}.

It is now live and open for student registrations.

— Centralized Club Portal"""
    )


def send_event_rejection_email(to, user_name, event_title, rejected_by, reason):
    send_email(
        to,
        f"Event Rejected: {event_title}",
        f"""Hello {user_name},

Unfortunately, your event "{event_title}" has been rejected by {rejected_by}.

Reason: {reason}

You may revise and resubmit the event.

— Centralized Club Portal"""
    )


def send_event_update_email(to, user_name, event_title, changes):
    send_email(
        to,
        f"Event Updated: {event_title}",
        f"""Hello {user_name},

The event "{event_title}" you registered for has been updated.

Changes: {changes}

Please review the updated details on the portal.

— Centralized Club Portal"""
    )


def send_event_cancellation_email(to, user_name, event_title):
    send_email(
        to,
        f"Event Cancelled: {event_title}",
        f"""Hello {user_name},

We regret to inform you that the event "{event_title}" has been cancelled.

We apologise for the inconvenience.

— Centralized Club Portal"""
    )
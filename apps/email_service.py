"""
email_service.py — Django email sending.
FIX: email_logs INSERT now uses correct column names from schema:
     (recipient, subject, sent_at)  NOT (email, subject, status)
"""
import ssl
from django.core.mail import send_mail as django_send_mail, get_connection
from django.conf import settings
from apps.db import get_cursor, close_connection


def _get_email_connection():
    """Create email connection with SSL verification disabled — fixes Python 3.14 SSL error."""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode    = ssl.CERT_NONE
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        ssl_context=ssl_context,
    )


def send_email(to, subject, body, html=None):
    try:
        connection = _get_email_connection()
        django_send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
            html_message=html,
            fail_silently=False,
            connection=connection,
        )
        success = True
    except Exception as e:
        print(f"Email send error: {e}")
        success = False

    # FIX: Schema is (id, recipient, subject, sent_at) — NOT (email, subject, status)
    # sent_at is auto-filled by DEFAULT CURRENT_TIMESTAMP so we only insert recipient+subject
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
        f"✅ Event Approved: {event_title}",
        f"""Hello {user_name},

Great news! Your event "{event_title}" has been approved by {approved_by}.

It is now live and open for student registrations.

— Centralized Club Portal"""
    )


def send_event_rejection_email(to, user_name, event_title, rejected_by, reason):
    send_email(
        to,
        f"❌ Event Rejected: {event_title}",
        f"""Hello {user_name},

Unfortunately, your event "{event_title}" has been rejected by {rejected_by}.

Reason: {reason}

You may revise and resubmit the event.

— Centralized Club Portal"""
    )


def send_event_update_email(to, user_name, event_title, changes):
    send_email(
        to,
        f"📝 Event Updated: {event_title}",
        f"""Hello {user_name},

The event "{event_title}" you registered for has been updated.

Changes: {changes}

Please review the updated details on the portal.

— Centralized Club Portal"""
    )


def send_event_cancellation_email(to, user_name, event_title):
    send_email(
        to,
        f"🚫 Event Cancelled: {event_title}",
        f"""Hello {user_name},

We regret to inform you that the event "{event_title}" has been cancelled.

We apologise for the inconvenience.

— Centralized Club Portal"""
    )

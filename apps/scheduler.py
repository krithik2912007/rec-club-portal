"""
scheduler.py — Background jobs identical to Flask version.
Uses django-apscheduler which integrates APScheduler with Django.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apps.db import get_cursor, close_connection
from apps.email_service import send_email
from datetime import date, datetime, timedelta

scheduler = BackgroundScheduler()


def send_24hr_reminders():
    tomorrow = date.today() + timedelta(days=1)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.id, e.title, e.date, e.time, e.location,
               u.name AS user_name, u.email AS user_email
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users u  ON r.user_id  = u.id
        WHERE e.date = %s AND e.status = 'approved' AND r.status = 'registered'
    """, (tomorrow,))
    rows = cursor.fetchall()
    close_connection(cursor, conn)
    for row in rows:
        try:
            send_email(
                row["user_email"],
                f"⏰ Reminder: {row['title']} is tomorrow!",
                f"""Hello {row['user_name']},

This is your 24-hour reminder that you are registered for:

Event  : {row['title']}
Date   : {row['date']}
Time   : {str(row['time'])[:5]}
Venue  : {row['location'] or '—'}

Make sure you are prepared. See you there!

— Centralized Club Portal"""
            )
        except Exception as e:
            print(f"[Scheduler] 24hr reminder failed for {row['user_email']}: {e}")


def send_1hr_reminders():
    now      = datetime.now()
    win_from = now + timedelta(minutes=55)
    win_to   = now + timedelta(minutes=70)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.id, e.title, e.date, e.time, e.location,
               u.name AS user_name, u.email AS user_email
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users u  ON r.user_id  = u.id
        WHERE e.status = 'approved' AND r.status = 'registered'
        AND CONCAT(e.date, ' ', e.time) BETWEEN %s AND %s
    """, (win_from.strftime("%Y-%m-%d %H:%M:%S"), win_to.strftime("%Y-%m-%d %H:%M:%S")))
    rows = cursor.fetchall()
    close_connection(cursor, conn)
    for row in rows:
        try:
            send_email(
                row["user_email"],
                f"🔔 Starting in 1 hour: {row['title']}",
                f"""Hello {row['user_name']},

Your event starts in approximately 1 hour!

Event  : {row['title']}
Date   : {row['date']}
Time   : {str(row['time'])[:5]}
Venue  : {row['location'] or '—'}

Please head over soon.

— Centralized Club Portal"""
            )
        except Exception as e:
            print(f"[Scheduler] 1hr reminder failed for {row['user_email']}: {e}")


def expire_stale_payments():
    cursor, conn = get_cursor()
    try:
        cursor.execute("UPDATE payments SET status='expired' WHERE status='pending' AND expires_at < NOW()")
        conn.commit()
    except Exception as e:
        print(f"[Scheduler] Payment expiry error: {e}")
    finally:
        close_connection(cursor, conn)


def purge_old_activity_logs():
    cursor, conn = get_cursor()
    try:
        cursor.execute("DELETE FROM activity_logs WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY)")
        deleted = cursor.rowcount
        conn.commit()
        if deleted > 0:
            print(f"[Scheduler] Purged {deleted} old activity log entries")
    except Exception as e:
        print(f"[Scheduler] Activity log purge error: {e}")
    finally:
        close_connection(cursor, conn)


def start_scheduler():
    scheduler.add_job(send_24hr_reminders,   CronTrigger(hour=8, minute=0),  id="reminder_24hr",      replace_existing=True)
    scheduler.add_job(send_1hr_reminders,    IntervalTrigger(minutes=15),     id="reminder_1hr",       replace_existing=True)
    scheduler.add_job(expire_stale_payments, IntervalTrigger(minutes=5),      id="expire_payments",    replace_existing=True)
    scheduler.add_job(purge_old_activity_logs, CronTrigger(hour=2, minute=0), id="purge_activity_logs",replace_existing=True)
    scheduler.start()
    print("✅ Scheduler started")

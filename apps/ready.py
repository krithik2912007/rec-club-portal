"""
apps/ready.py — Called from AppConfig.ready() to start the APScheduler.
Only starts in the main process (not manage.py commands or reloader child processes).
"""
import os


def start_background_jobs():
    # Prevent double-start in Django's autoreload (runs twice in dev mode)
    if os.environ.get("RUN_MAIN") == "true" or not os.environ.get("DJANGO_AUTORELOAD"):
        from apps.scheduler import start_scheduler
        try:
            start_scheduler()
        except Exception as e:
            print(f"[Scheduler] Failed to start: {e}")

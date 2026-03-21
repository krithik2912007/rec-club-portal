from django.shortcuts import render, redirect
from django.http import JsonResponse
from apps.db import get_cursor, close_connection, serialize_rows
from apps.decorators import login_required, admin_required


# ── PUBLIC PAGES ──
def index(request):
    return render(request, "index.html")

def home(request):
    return render(request, "home.html")

def clubs_page(request):
    return render(request, "clubs.html")

def events_page(request):
    return render(request, "events.html")

def calendar_page(request):
    return render(request, "calendar.html")

def club_detail_page(request, club_id):
    return render(request, "club.html")

def event_detail_page(request, event_id):
    return render(request, "event.html")

def reset_password_page(request, token):
    return render(request, "reset_password.html", {"token": token})


# ── PROTECTED PAGES ──
@login_required
def dashboard(request):
    return render(request, "dashboard.html")

@login_required
def club_dashboard(request):
    cursor, conn = get_cursor()
    cursor.execute(
        "SELECT id FROM club_memberships WHERE user_id=%s LIMIT 1",
        (request.session["user_id"],)
    )
    member = cursor.fetchone()
    close_connection(cursor, conn)
    if not member:
        return render(request, "dashboard.html")
    return render(request, "club_dashboard.html")

@admin_required
def admin_dashboard(request):
    return render(request, "admin.html")


# ── STATS API ──
def get_stats(request):
    cursor, conn = get_cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM clubs")
    clubs = cursor.fetchone()["count"]
    cursor.execute("SELECT COUNT(*) AS count FROM events WHERE status='approved'")
    events = cursor.fetchone()["count"]
    cursor.execute("SELECT COUNT(*) AS count FROM users")
    members = cursor.fetchone()["count"]
    close_connection(cursor, conn)
    return JsonResponse({"clubs": clubs, "events": events, "members": members})


# ── UPCOMING EVENTS API ──
def upcoming_events(request):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.*, c.name AS club_name FROM events e
        JOIN clubs c ON e.club_id=c.id
        WHERE e.status='approved' AND e.date >= CURDATE()
        ORDER BY e.date ASC LIMIT 3
    """)
    events = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)


# ── ADMIN STATS API ──
@admin_required
def admin_stats(request):
    cursor, conn = get_cursor()
    cursor.execute("SELECT COUNT(*) AS total FROM clubs")
    clubs = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM events")
    events = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM registrations")
    registrations = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) AS total FROM events WHERE status='approved' AND date >= CURDATE()")
    upcoming = cursor.fetchone()["total"]
    close_connection(cursor, conn)
    return JsonResponse({"clubs": clubs, "events": events, "registrations": registrations, "upcoming": upcoming})


def attendance_scan_page(request, event_id):
    return render(request, 'attendance_scan.html', {'event_id': event_id})

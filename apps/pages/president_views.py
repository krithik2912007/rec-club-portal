"""
club_president_routes.py → Django views
All president/VP actions: pending changes, member management, notifications.
"""
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from apps.db import get_cursor, close_connection, serialize_row, serialize_rows, log_activity
from apps.decorators import login_required, president_required, coordinator_required, is_leadership


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


# ── PENDING CHANGES queue (president approves VP edits) ──
@login_required
def get_pending_changes(request, club_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT pc.*, u.name AS changed_by_name
        FROM pending_changes pc JOIN users u ON pc.changed_by=u.id
        WHERE pc.club_id=%s AND pc.status='pending'
        ORDER BY pc.created_at DESC
    """, (club_id,))
    changes = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(changes, safe=False)


@csrf_exempt
@login_required
def approve_pending_change(request, club_id, change_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("SELECT role FROM club_memberships WHERE user_id=%s AND club_id=%s",
                   (request.session["user_id"], club_id))
    member = cursor.fetchone()
    if not member or member["role"] != "president":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only president can approve changes"}, status=403)
    cursor.execute("SELECT * FROM pending_changes WHERE id=%s AND club_id=%s AND status='pending'",
                   (change_id, club_id))
    change = cursor.fetchone()
    if not change:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Change not found"}, status=404)
    if change["change_type"] == "event_edit":
        payload = json.loads(change["payload"])
        cursor.execute("""
            UPDATE events SET title=%s, description=%s, date=%s, time=%s,
                location=%s, type=%s, capacity=%s WHERE id=%s
        """, (payload.get("title"), payload.get("description"), payload.get("date"),
              payload.get("time"), payload.get("location"), payload.get("type"),
              payload.get("capacity"), change["target_id"]))
    cursor.execute("UPDATE pending_changes SET status='approved' WHERE id=%s", (change_id,))
    log_activity(cursor, f"President {request.session['user_id']} approved pending change {change_id}")
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Change approved and applied"})


@csrf_exempt
@login_required
def reject_pending_change(request, club_id, change_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("SELECT role FROM club_memberships WHERE user_id=%s AND club_id=%s",
                   (request.session["user_id"], club_id))
    member = cursor.fetchone()
    if not member or member["role"] != "president":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only president can reject changes"}, status=403)
    cursor.execute("UPDATE pending_changes SET status='rejected' WHERE id=%s AND club_id=%s",
                   (change_id, club_id))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Change rejected"})


# ── PRESIDENT APPROVE / REJECT EVENT ──
@csrf_exempt
@login_required
def president_approve_event(request, event_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT cm.role FROM events e
        JOIN club_memberships cm ON cm.club_id=e.club_id AND cm.user_id=%s
        WHERE e.id=%s
    """, (request.session["user_id"], event_id))
    role = cursor.fetchone()
    if not role or role["role"] != "president":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only president can approve"}, status=403)
    cursor.execute("UPDATE events SET president_approved=TRUE, status='pending_admin' WHERE id=%s AND status='pending_president'", (event_id,))
    log_activity(cursor, f"Event {event_id} approved by president {request.session['user_id']}")
    conn.commit()
    cursor.execute("SELECT e.title, u.name, u.email, p.name AS president_name FROM events e JOIN users u ON e.created_by=u.id JOIN users p ON p.id=%s WHERE e.id=%s",
                   (request.session["user_id"], event_id))
    info = cursor.fetchone()
    close_connection(cursor, conn)
    if info:
        from apps.email_service import send_event_approval_email
        try:
            send_event_approval_email(info["email"], info["name"], info["title"], f"President {info['president_name']}")
        except Exception:
            pass
    return JsonResponse({"message": "Event approved by president"})


@csrf_exempt
@login_required
def president_reject_event(request, event_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data   = _json(request)
    reason = data.get("reason")
    if not reason:
        return JsonResponse({"message": "Rejection reason required"}, status=400)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT cm.role FROM events e
        JOIN club_memberships cm ON cm.club_id=e.club_id AND cm.user_id=%s WHERE e.id=%s
    """, (request.session["user_id"], event_id))
    role = cursor.fetchone()
    if not role or role["role"] != "president":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only president can reject"}, status=403)
    cursor.execute("UPDATE events SET status='rejected', president_rejection_reason=%s WHERE id=%s", (reason, event_id))
    log_activity(cursor, f"Event {event_id} rejected by president {request.session['user_id']}: {reason}")
    conn.commit()
    cursor.execute("SELECT e.title, u.name, u.email, p.name AS president_name FROM events e JOIN users u ON e.created_by=u.id JOIN users p ON p.id=%s WHERE e.id=%s",
                   (request.session["user_id"], event_id))
    info = cursor.fetchone()
    close_connection(cursor, conn)
    if info:
        from apps.email_service import send_event_rejection_email
        try:
            send_event_rejection_email(info["email"], info["name"], info["title"], f"President {info['president_name']}", reason)
        except Exception:
            pass
    return JsonResponse({"message": "Event rejected by president"})


# ── PENDING EVENTS FOR CLUB ──
@login_required
def get_pending_events(request, club_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.id, e.title, e.date, e.time, e.president_approved, e.admin_approved,
               e.status, c.name AS club_name
        FROM events e JOIN clubs c ON e.club_id=c.id
        WHERE e.club_id=%s AND e.status IN ('pending_president','pending_admin')
        ORDER BY e.date ASC
    """, (club_id,))
    events = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)


# ── NOTIFICATIONS ──
@login_required
def get_notifications(request):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT id, message, is_read, created_at FROM notifications
        WHERE user_id=%s ORDER BY created_at DESC LIMIT 50
    """, (user_id,))
    notifications = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(notifications, safe=False)


@csrf_exempt
@login_required
def mark_notification_read(request, notif_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("UPDATE notifications SET is_read=TRUE WHERE id=%s AND user_id=%s",
                   (notif_id, request.session["user_id"]))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Notification marked as read"})


@csrf_exempt
@login_required
def mark_all_notifications_read(request):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("UPDATE notifications SET is_read=TRUE WHERE user_id=%s", (request.session["user_id"],))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "All notifications marked as read"})


# ── MY COORDINATOR EVENTS ──
@login_required
def my_coordinator_events(request):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.*, c.name AS club_name, COUNT(r.id) AS registered_count
        FROM event_coordinators ec JOIN events e ON ec.event_id=e.id
        JOIN clubs c ON e.club_id=c.id
        LEFT JOIN registrations r ON r.event_id=e.id AND r.status='registered'
        WHERE ec.user_id=%s GROUP BY e.id ORDER BY e.date DESC
    """, (user_id,))
    events = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)

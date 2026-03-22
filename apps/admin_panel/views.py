import json
import uuid
import os
import io
from datetime import datetime, date as date_type
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings as djsettings
from apps.db import get_cursor, close_connection, serialize_row, serialize_rows, log_activity
from apps.decorators import admin_required, login_required
from apps.email_service import send_email, send_event_approval_email, send_event_rejection_email

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}

def _save_upload(file):
    filename = str(uuid.uuid4()) + "_" + file.name
    path     = os.path.join(djsettings.MEDIA_ROOT, "uploads", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb+") as f:
        for chunk in file.chunks():
            f.write(chunk)
    return "uploads/" + filename


# ═══════════════════════════════════
# CLUB MANAGEMENT
# ═══════════════════════════════════
@csrf_exempt
@admin_required
def admin_clubs(request):
    if request.method == "GET":
        cursor, conn = get_cursor()
        cursor.execute("SELECT id,name,category,description,about,vision,mission,image FROM clubs ORDER BY name ASC")
        # FIX: use serialize_rows so DATE/Decimal fields don't crash JSON serialization
        clubs = serialize_rows(cursor.fetchall())
        close_connection(cursor, conn)
        return JsonResponse(clubs, safe=False)

    if request.method == "POST":
        name        = request.POST.get("name")
        category    = request.POST.get("category")
        description = request.POST.get("description")
        about       = request.POST.get("about")
        vision      = request.POST.get("vision")
        mission     = request.POST.get("mission")
        if not name:
            return JsonResponse({"message": "Club name required"}, status=400)
        image      = request.FILES.get("image")
        image_path = _save_upload(image) if image and _allowed(image.name) else None
        cursor, conn = get_cursor()
        cursor.execute(
            "INSERT INTO clubs(name, category, description, about, vision, mission, image) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (name, category, description, about, vision, mission, image_path)
        )
        conn.commit()
        club_id = cursor.lastrowid
        standard_roles = ['president','vice_president','secretary','joint_secretary','treasurer','hr',
                          'event_coordinator','event_management_head','event_management_associate',
                          'pr_head','pr_associate','photography']
        for r in standard_roles:
            try:
                cursor.execute("INSERT IGNORE INTO club_roles(club_id, role_name, is_standard) VALUES(%s,%s,TRUE)", (club_id, r))
            except Exception:
                pass
        log_activity(cursor, f"Admin {request.session['user_id']} created club '{name}'")
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Club added"})

    return JsonResponse({"message": "Method not allowed"}, status=405)


@csrf_exempt
@admin_required
def admin_club_detail(request, club_id):
    if request.method == "PUT":
        name = category = description = about = vision = mission = None
        image = None

        content_type = request.content_type or ""

        if "multipart" in content_type:
            from django.http.multipartparser import MultiPartParser
            parser = MultiPartParser(request.META, request, request.upload_handlers)
            post_data, file_data = parser.parse()
            name        = post_data.get("name")
            category    = post_data.get("category")
            description = post_data.get("description")
            about       = post_data.get("about")
            vision      = post_data.get("vision")
            mission     = post_data.get("mission")
            image       = file_data.get("image")
        else:
            try:
                data        = json.loads(request.body)
                name        = data.get("name")
                category    = data.get("category")
                description = data.get("description")
                about       = data.get("about")
                vision      = data.get("vision")
                mission     = data.get("mission")
            except Exception:
                pass

        if not name:
            return JsonResponse({"message": "Club name is required"}, status=400)

        cursor, conn = get_cursor()
        if image and _allowed(image.name):
            image_path = _save_upload(image)
            cursor.execute("""
                UPDATE clubs SET name=%s, category=%s, description=%s, about=%s,
                                 vision=%s, mission=%s, image=%s WHERE id=%s
            """, (name, category, description, about, vision, mission, image_path, club_id))
        else:
            cursor.execute("""
                UPDATE clubs SET name=%s, category=%s, description=%s, about=%s,
                                 vision=%s, mission=%s WHERE id=%s
            """, (name, category, description, about, vision, mission, club_id))

        log_activity(cursor, f"Admin {request.session['user_id']} updated club {club_id}")
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Club updated"})

    if request.method == "DELETE":
        cursor, conn = get_cursor()
        cursor.execute("DELETE FROM clubs WHERE id=%s", (club_id,))
        log_activity(cursor, f"Admin {request.session['user_id']} deleted club {club_id}")
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Club deleted"})

    return JsonResponse({"message": "Method not allowed"}, status=405)

@csrf_exempt
@admin_required
def admin_club_members(request, club_id):
    if request.method == "GET":
        cursor, conn = get_cursor()
        cursor.execute("""
            SELECT u.id, u.name, u.email, u.reg_no, u.department, u.year, cm.role
            FROM club_memberships cm JOIN users u ON cm.user_id=u.id
            WHERE cm.club_id=%s
            ORDER BY FIELD(cm.role,'president','vice_president','secretary','joint_secretary',
                           'treasurer','hr','event_coordinator','event_management_head',
                           'event_management_associate','pr_head','pr_associate','photography'),
                     u.name ASC
        """, (club_id,))
        # FIX: serialize so dict rows are proper JSON-safe dicts
        members = serialize_rows(cursor.fetchall())
        close_connection(cursor, conn)
        return JsonResponse(members, safe=False)

    if request.method == "POST":
        data    = _json(request)
        user_id = data.get("user_id")
        role    = data.get("role")
        cursor, conn = get_cursor()
        try:
            cursor.execute("INSERT INTO club_memberships(user_id, club_id, role) VALUES(%s,%s,%s)", (user_id, club_id, role))
            conn.commit()
        except Exception:
            close_connection(cursor, conn)
            return JsonResponse({"message": "User already in club"}, status=400)
        close_connection(cursor, conn)
        return JsonResponse({"message": "Member added"})

    return JsonResponse({"message": "Method not allowed"}, status=405)


@csrf_exempt
@admin_required
def admin_club_member_detail(request, club_id, user_id):
    if request.method == "PUT":
        data     = _json(request)
        new_role = data.get("role")
        if not new_role:
            return JsonResponse({"message": "Role required"}, status=400)
        cursor, conn = get_cursor()
        cursor.execute("UPDATE club_memberships SET role=%s WHERE user_id=%s AND club_id=%s", (new_role, user_id, club_id))
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Member role updated"})

    if request.method == "DELETE":
        cursor, conn = get_cursor()
        cursor.execute("DELETE FROM club_memberships WHERE user_id=%s AND club_id=%s", (user_id, club_id))
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Member removed"})

    return JsonResponse({"message": "Method not allowed"}, status=405)


# ═══════════════════════════════════
# EVENT MANAGEMENT
# ═══════════════════════════════════
@csrf_exempt
@admin_required
def admin_events(request):
    if request.method == "GET":
        cursor, conn = get_cursor()
        cursor.execute("""
            SELECT e.*, c.name AS club_name, COUNT(r.id) AS registered_count
            FROM events e JOIN clubs c ON e.club_id=c.id
            LEFT JOIN registrations r ON r.event_id=e.id
            GROUP BY e.id ORDER BY e.date ASC
        """)
        events = serialize_rows(cursor.fetchall())
        close_connection(cursor, conn)
        return JsonResponse(events, safe=False)

    if request.method == "POST":
        data = _json(request)
        def _int_or_none(val):
            try:
                v = int(val); return v if v > 0 else None
            except: return None
        cursor, conn = get_cursor()
        cursor.execute("""
            INSERT INTO events(club_id, created_by, title, description, date, time, location, type,
                capacity, event_category, min_members, max_members, is_paid, price,
                prize_pool, about, rules, instructions, agenda,
                president_approved, admin_approved, status)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,TRUE,'approved')
        """, (data.get("club_id"), request.session["user_id"], data.get("title"), data.get("description"),
              data.get("date"), data.get("time"), data.get("location"), data.get("type"),
              _int_or_none(data.get("capacity")),
              data.get("event_category","individual"),
              _int_or_none(data.get("min_members")), _int_or_none(data.get("max_members")),
              bool(data.get("is_paid",False)), data.get("price") or 0,
              data.get("prize_pool"), data.get("about"), data.get("rules"),
              data.get("instructions"), data.get("agenda")))
        log_activity(cursor, f"Admin {request.session['user_id']} created event directly as approved")
        conn.commit()
        event_id = cursor.lastrowid
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event created", "event_id": event_id})

    return JsonResponse({"message": "Method not allowed"}, status=405)


@csrf_exempt
@admin_required
def admin_event_detail(request, event_id):
    if request.method == "PUT":
        data = _json(request)
        cursor, conn = get_cursor()
        cursor.execute("""
            UPDATE events SET title=%s, description=%s, date=%s, time=%s, location=%s, type=%s,
                capacity=%s, event_category=%s, min_members=%s, max_members=%s,
                is_paid=%s, price=%s, prize_pool=%s, about=%s, rules=%s, instructions=%s, agenda=%s
            WHERE id=%s
        """, (data.get("title"), data.get("description"), data.get("date"), data.get("time"),
              data.get("location"), data.get("type"), data.get("capacity"),
              data.get("event_category","individual"),
              data.get("min_members") or None, data.get("max_members") or None,
              bool(data.get("is_paid",False)), data.get("price") or 0,
              data.get("prize_pool"), data.get("about"), data.get("rules"),
              data.get("instructions"), data.get("agenda"), event_id))
        log_activity(cursor, f"Admin {request.session['user_id']} updated event {event_id}")
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event updated"})

    if request.method == "DELETE":
        cursor, conn = get_cursor()
        cursor.execute("DELETE FROM events WHERE id=%s", (event_id,))
        log_activity(cursor, f"Admin {request.session['user_id']} deleted event {event_id}")
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event deleted"})

    return JsonResponse({"message": "Method not allowed"}, status=405)


@csrf_exempt
@admin_required
def admin_approve_event(request, event_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("UPDATE events SET admin_approved=TRUE, status='approved' WHERE id=%s AND status='pending_admin'", (event_id,))
    conn.commit()
    cursor.execute("SELECT e.title, u.name, u.email FROM events e JOIN users u ON e.created_by=u.id WHERE e.id=%s", (event_id,))
    info = cursor.fetchone()
    if info:
        log_activity(cursor, f"Admin approved event: '{info['title']}' (notified {info['name']})")
        conn.commit()
    close_connection(cursor, conn)
    if info:
        try:
            send_event_approval_email(info["email"], info["name"], info["title"], "Admin")
        except Exception:
            pass
    return JsonResponse({"message": "Event approved"})


@csrf_exempt
@admin_required
def admin_reject_event(request, event_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data   = _json(request)
    reason = data.get("reason")
    if not reason:
        return JsonResponse({"message": "Rejection reason required"}, status=400)
    cursor, conn = get_cursor()
    cursor.execute("UPDATE events SET status='rejected', admin_rejection_reason=%s WHERE id=%s", (reason, event_id))
    conn.commit()
    cursor.execute("SELECT e.title, u.name, u.email FROM events e JOIN users u ON e.created_by=u.id WHERE e.id=%s", (event_id,))
    info = cursor.fetchone()
    if info:
        log_activity(cursor, f"Admin rejected event: '{info['title']}' — Reason: {reason}")
        conn.commit()
    close_connection(cursor, conn)
    if info:
        try:
            send_event_rejection_email(info["email"], info["name"], info["title"], "Admin", reason)
        except Exception:
            pass
    return JsonResponse({"message": "Event rejected by admin"})


@csrf_exempt
@admin_required
def admin_upload_gallery(request, event_id):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    image = request.FILES.get("image")
    if not image or not _allowed(image.name):
        return JsonResponse({"message": "Invalid image"}, status=400)
    image_path = _save_upload(image)
    cursor, conn = get_cursor()
    cursor.execute("INSERT INTO event_gallery(event_id, image_url) VALUES(%s,%s)", (event_id, image_path))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Image uploaded"})


@csrf_exempt
@admin_required
def admin_delete_gallery_image(request, event_id, image_id):
    if request.method != "DELETE":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("SELECT image_url FROM event_gallery WHERE id=%s AND event_id=%s", (image_id, event_id))
    img = cursor.fetchone()
    if not img:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Image not found"}, status=404)
    cursor.execute("DELETE FROM event_gallery WHERE id=%s", (image_id,))
    conn.commit()
    close_connection(cursor, conn)
    try:
        filepath = os.path.join(djsettings.MEDIA_ROOT, img["image_url"])
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass
    return JsonResponse({"message": "Image deleted"})


@csrf_exempt
@admin_required
def admin_apply_pending_edit(request, event_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data = _json(request)
    cursor, conn = get_cursor()
    if data.get("capacity"):
        cursor.execute("SELECT COUNT(*) AS total FROM registrations WHERE event_id=%s AND status='registered'", (event_id,))
        reg_count = cursor.fetchone()["total"]
        if int(data["capacity"]) < reg_count:
            close_connection(cursor, conn)
            return JsonResponse({"message": f"Capacity cannot be less than current registrations ({reg_count})"}, status=400)
    cursor.execute("""
        UPDATE events SET location=%s, date=%s, time=%s, type=%s, capacity=%s,
            description=%s, prize_pool=%s, about=%s, rules=%s, instructions=%s WHERE id=%s
    """, (data.get("location"), data.get("date"), data.get("time"), data.get("type"),
          data.get("capacity") or None, data.get("description"), data.get("prize_pool"),
          data.get("about"), data.get("rules"), data.get("instructions"), event_id))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Event updated by admin"})


@admin_required
def admin_pending_events(request):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.id, e.title, e.date, e.time, e.president_approved, e.admin_approved, e.status,
               c.name AS club_name, COUNT(r.id) AS registered_count
        FROM events e JOIN clubs c ON e.club_id=c.id
        LEFT JOIN registrations r ON r.event_id=e.id
        WHERE e.status='pending_admin'
        GROUP BY e.id, e.title, e.date, e.time, e.president_approved, e.admin_approved, e.status, c.name
        ORDER BY e.date ASC
    """)
    events = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)


# ═══════════════════════════════════
# ANALYTICS
# ═══════════════════════════════════
@admin_required
def admin_event_analytics(request):
    days  = request.GET.get("days")
    try: days = int(days)
    except: days = None
    cursor, conn = get_cursor()
    _dcond = "AND r.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)" if days else ""
    cursor.execute(
        "SELECT e.id, e.title, e.capacity, COUNT(DISTINCT r.id) AS registrations,"
        " ROUND(AVG(f.rating),1) AS avg_rating, COUNT(DISTINCT f.id) AS feedback_count"
        " FROM events e"
        " LEFT JOIN registrations r ON r.event_id=e.id AND r.status='registered' " + _dcond +
        " LEFT JOIN event_feedback f ON f.event_id=e.id"
        " GROUP BY e.id, e.title, e.capacity ORDER BY registrations DESC LIMIT 10",
        (days,) if days else ()
    )
    # FIX: serialize_rows to handle Decimal/DATE fields properly
    events = serialize_rows(cursor.fetchall())
    for ev in events:
        cap  = ev.get("capacity") or 0
        regs = ev.get("registrations") or 0
        ev["fill_rate"] = round((regs / cap * 100), 1) if cap > 0 else None

    cursor.execute("SELECT c.name, COUNT(r.id) AS total FROM clubs c JOIN events e ON e.club_id=c.id LEFT JOIN registrations r ON r.event_id=e.id GROUP BY c.id ORDER BY total DESC LIMIT 1")
    club = cursor.fetchone()

    cursor.execute("SELECT DATE(created_at) AS day, COUNT(*) AS total FROM registrations GROUP BY day ORDER BY day ASC LIMIT 14")
    raw_trend = cursor.fetchall()
    trend = [{"day": str(t["day"]), "total": t["total"]} for t in raw_trend]

    cursor.execute("""
        SELECT MONTHNAME(created_at) AS active_month, COUNT(*) AS total
        FROM registrations GROUP BY active_month ORDER BY total DESC LIMIT 1
    """)
    month_row = cursor.fetchone()

    cursor.execute("""
        SELECT DAYNAME(created_at) AS active_day, COUNT(*) AS total
        FROM registrations GROUP BY active_day ORDER BY total DESC LIMIT 1
    """)
    day_row = cursor.fetchone()

    total_regs = sum((e.get("registrations") or 0) for e in events)
    avg_regs   = round(total_regs / len(events)) if events else 0
    close_connection(cursor, conn)
    return JsonResponse({
        "events":           events,
        "most_popular":     events[0]["title"] if events else "N/A",
        "least_popular":    events[-1]["title"] if events else "N/A",
        "average":          avg_regs,
        "most_active_club": club["name"] if club else "N/A",
        "trend":            trend,
        "active_month":     month_row["active_month"] if month_row else "N/A",
        "active_day":       day_row["active_day"] if day_row else "N/A",
    })


@admin_required
def admin_favorite_analytics(request):
    cursor, conn = get_cursor()
    cursor.execute("SELECT c.name, COUNT(fc.id) AS favorites FROM favorite_clubs fc JOIN clubs c ON fc.club_id=c.id GROUP BY c.id ORDER BY favorites DESC LIMIT 5")
    # FIX: serialize_rows so MySQL DictRow objects become proper JSON-safe dicts
    clubs = serialize_rows(cursor.fetchall())
    cursor.execute("SELECT e.title, COUNT(fe.id) AS favorites FROM favorite_events fe JOIN events e ON fe.event_id=e.id GROUP BY e.id ORDER BY favorites DESC LIMIT 5")
    events = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse({"clubs": clubs or [], "events": events or []})


@admin_required
def admin_revenue_analytics(request):
    days = request.GET.get("days")
    try: days = int(days)
    except: days = None
    date_cond = "AND p.completed_at >= DATE_SUB(NOW(), INTERVAL %s DAY)" if days else ""
    cursor, conn = get_cursor()

    cursor.execute("SELECT COALESCE(SUM(p.amount),0) AS total_revenue, COUNT(p.id) AS total_transactions FROM payments p WHERE p.status='success' " + date_cond, (days,) if days else ())
    totals = cursor.fetchone()

    cursor.execute("SELECT c.name AS club_name, COALESCE(SUM(p.amount),0) AS revenue, COUNT(p.id) AS transactions FROM payments p JOIN events e ON p.event_id=e.id JOIN clubs c ON e.club_id=c.id WHERE p.status='success' GROUP BY c.id ORDER BY revenue DESC LIMIT 8")
    # FIX: serialize so Decimal revenue values are JSON-serializable
    by_club = [{"club_name": r["club_name"], "revenue": float(r["revenue"]), "transactions": r["transactions"]} for r in cursor.fetchall()]

    cursor.execute("SELECT DATE(completed_at) AS day, COALESCE(SUM(amount),0) AS revenue FROM payments WHERE status='success' AND completed_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) GROUP BY DATE(completed_at) ORDER BY day ASC")
    raw_trend = cursor.fetchall()
    trend = [{"day": str(t["day"]), "revenue": float(t["revenue"])} for t in raw_trend]

    cursor.execute("SELECT status, COUNT(*) AS cnt, COALESCE(SUM(amount),0) AS amount FROM payments GROUP BY status")
    raw_status = cursor.fetchall()
    status_breakdown = [{"status": s["status"], "count": s["cnt"], "amount": float(s["amount"])} for s in raw_status]

    cursor.execute("""
        SELECT e.title, c.name AS club_name,
               COALESCE(SUM(p.amount),0) AS revenue,
               COUNT(p.id) AS registrations
        FROM payments p
        JOIN events e ON p.event_id=e.id
        JOIN clubs c ON e.club_id=c.id
        WHERE p.status='success'
        GROUP BY e.id, e.title, c.name
        ORDER BY revenue DESC LIMIT 5
    """)
    raw_top = cursor.fetchall()
    top_events = [{"title": t["title"], "club_name": t["club_name"], "revenue": float(t["revenue"]), "registrations": t["registrations"]} for t in raw_top]

    cursor.execute("SELECT COALESCE(SUM(amount),0) AS pending_amount, COUNT(*) AS pending_count FROM payments WHERE status='pending'")
    pending = cursor.fetchone()

    close_connection(cursor, conn)
    return JsonResponse({
        "total_revenue":      float(totals["total_revenue"]),
        "total_transactions": totals["total_transactions"],
        "by_club":            by_club,
        "trend":              trend,
        "status_breakdown":   status_breakdown,
        "top_events":         top_events,
        "pending_amount":     float(pending["pending_amount"]),
        "pending_count":      pending["pending_count"],
    })


# ═══════════════════════════════════
# USERS
# ═══════════════════════════════════
@admin_required
def admin_all_users(request):
    cursor, conn = get_cursor()
    cursor.execute("SELECT id, reg_no, name, email, role, department, year, phone, bio, github, linkedin, instagram, profile_pic, created_at FROM users ORDER BY created_at DESC")
    users = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(users, safe=False)


@csrf_exempt
@admin_required
def admin_user_detail(request, user_id):
    if request.method == "DELETE":
        if user_id == request.session["user_id"]:
            return JsonResponse({"message": "Cannot delete your own account"}, status=400)
        cursor, conn = get_cursor()
        cursor.execute("SELECT role FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        if not user:
            close_connection(cursor, conn)
            return JsonResponse({"message": "User not found"}, status=404)
        if user["role"] == "admin":
            close_connection(cursor, conn)
            return JsonResponse({"message": "Cannot delete another admin account"}, status=403)
        cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
        log_activity(cursor, f"Admin {request.session['user_id']} deleted user {user_id}")
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "User deleted successfully"})

    if request.method == "PUT":
        # FIX: support both JSON body and form data for PUT
        content_type = request.content_type or ""
        if "application/json" in content_type:
            data = _json(request)
        else:
            data = request.POST
        cursor, conn = get_cursor()
        cursor.execute("SELECT role FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        if not user:
            close_connection(cursor, conn)
            return JsonResponse({"message": "User not found"}, status=404)
        cursor.execute("UPDATE users SET name=%s, department=%s, year=%s, phone=%s, bio=%s WHERE id=%s",
                       (data.get("name"), data.get("department") or None,
                        int(data.get("year")) if data.get("year") else None,
                        data.get("phone") or None, data.get("bio") or None, user_id))
        log_activity(cursor, f"Admin {request.session['user_id']} edited profile of user {user_id}")
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "User profile updated"})

    return JsonResponse({"message": "Method not allowed"}, status=405)


@csrf_exempt
@admin_required
def admin_promote_user(request, user_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    if user_id == request.session["user_id"]:
        return JsonResponse({"message": "You are already an admin"}, status=400)
    cursor, conn = get_cursor()
    cursor.execute("SELECT name, role FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    if not user:
        close_connection(cursor, conn)
        return JsonResponse({"message": "User not found"}, status=404)
    if user["role"] == "admin":
        close_connection(cursor, conn)
        return JsonResponse({"message": "User is already an admin"}, status=400)
    cursor.execute("UPDATE users SET role='admin' WHERE id=%s", (user_id,))
    log_activity(cursor, f"Admin {request.session['user_id']} promoted user {user_id} to admin")
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": f"{user['name']} has been promoted to admin"})


# ═══════════════════════════════════
# ACTIVITY & MISC
# ═══════════════════════════════════
@admin_required
def admin_activity(request):
    cursor, conn = get_cursor()
    try:
        cursor.execute("SELECT message, actor_id, entity_type, entity_id, created_at FROM activity_logs ORDER BY created_at DESC LIMIT 200")
    except Exception:
        cursor.execute("SELECT message, NULL AS actor_id, NULL AS entity_type, NULL AS entity_id, created_at FROM activity_logs ORDER BY created_at DESC LIMIT 200")
    logs = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(logs, safe=False)


@admin_required
def admin_rejected_events(request):
    period = request.GET.get("period", "24h")
    cursor, conn = get_cursor()
    cutoff_map = {"24h": "NOW() - INTERVAL 1 DAY", "7d": "NOW() - INTERVAL 7 DAY", "30d": "NOW() - INTERVAL 30 DAY"}
    cutoff = cutoff_map.get(period)
    if cutoff:
        cursor.execute(f"""
            SELECT e.id, e.title, e.date, e.time, e.status,
                   e.president_rejection_reason, e.admin_rejection_reason,
                   e.created_at, c.name AS club_name
            FROM events e JOIN clubs c ON e.club_id=c.id
            WHERE e.status='rejected' AND e.created_at >= {cutoff}
            ORDER BY e.created_at DESC
        """)
    else:
        cursor.execute("""
            SELECT e.id, e.title, e.date, e.time, e.status,
                   e.president_rejection_reason, e.admin_rejection_reason,
                   e.created_at, c.name AS club_name
            FROM events e JOIN clubs c ON e.club_id=c.id
            WHERE e.status='rejected' ORDER BY e.created_at DESC LIMIT 100
        """)
    events = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)


@admin_required
def admin_pending_changes(request):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT pc.*, u.name AS changed_by_name, c.name AS club_name
        FROM pending_changes pc JOIN users u ON pc.changed_by=u.id JOIN clubs c ON pc.club_id=c.id
        WHERE pc.status='pending' ORDER BY pc.created_at DESC
    """)
    changes = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(changes, safe=False)


@admin_required
def admin_test_email(request):
    send_email(djsettings.EMAIL_HOST_USER, "Test Email", "Email system working correctly.")
    return JsonResponse({"message": "Email sent"})


# ═══════════════════════════════════
# CLUB ROLES
# ═══════════════════════════════════
@csrf_exempt
@login_required
def club_roles(request, club_id):
    if request.method == "GET":
        cursor, conn = get_cursor()
        cursor.execute("SELECT id, role_name, is_standard FROM club_roles WHERE club_id=%s ORDER BY is_standard DESC, role_name ASC", (club_id,))
        # FIX: serialize_rows
        roles = serialize_rows(cursor.fetchall())
        close_connection(cursor, conn)
        return JsonResponse(roles, safe=False)

    if request.method == "POST":
        if request.session.get("role") != "admin":
            return JsonResponse({"message": "Admin access required"}, status=403)
        data      = _json(request)
        role_name = (data.get("role_name") or "").strip()
        if not role_name:
            return JsonResponse({"message": "Role name required"}, status=400)
        cursor, conn = get_cursor()
        try:
            cursor.execute("INSERT INTO club_roles(club_id, role_name, is_standard, created_by) VALUES(%s,%s,FALSE,%s)",
                           (club_id, role_name, request.session["user_id"]))
            conn.commit()
        except Exception:
            close_connection(cursor, conn)
            return JsonResponse({"message": "Role already exists for this club"}, status=400)
        close_connection(cursor, conn)
        return JsonResponse({"message": "Role added", "role_name": role_name})

    return JsonResponse({"message": "Method not allowed"}, status=405)


@csrf_exempt
def club_role_detail(request, club_id, role_name):
    if request.method != "DELETE":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    if request.session.get("role") != "admin":
        return JsonResponse({"message": "Admin access required"}, status=403)
    cursor, conn = get_cursor()
    cursor.execute("SELECT is_standard FROM club_roles WHERE club_id=%s AND role_name=%s", (club_id, role_name))
    row = cursor.fetchone()
    if not row:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Role not found"}, status=404)
    if row["is_standard"]:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Cannot delete a standard role"}, status=400)
    cursor.execute("DELETE FROM club_roles WHERE club_id=%s AND role_name=%s", (club_id, role_name))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Role deleted"})


# ═══════════════════════════════════
# SERVE UPLOADED FILES
# ═══════════════════════════════════
def serve_upload(request, filename):
    filepath = os.path.join(djsettings.MEDIA_ROOT, "uploads", filename)
    if not os.path.exists(filepath):
        return JsonResponse({"message": "File not found"}, status=404)
    with open(filepath, "rb") as f:
        import mimetypes
        content_type, _ = mimetypes.guess_type(filepath)
        return HttpResponse(f.read(), content_type=content_type or "application/octet-stream")
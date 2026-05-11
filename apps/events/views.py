import json
import uuid
import os
import io
from datetime import datetime, timedelta, date as date_type
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings as djsettings
from apps.db import get_cursor, close_connection, serialize_row, serialize_rows, log_activity
from apps.decorators import login_required
from apps.email_service import send_event_approval_email, send_event_rejection_email

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


# ── GET ALL APPROVED EVENTS ──
def get_events(request):
    user_id = request.session.get("user_id")
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.*, c.name AS club_name, COUNT(r.id) AS registered_count,
               CASE WHEN fe.user_id IS NULL THEN FALSE ELSE TRUE END AS is_favorited
        FROM events e
        JOIN clubs c ON e.club_id=c.id
        LEFT JOIN registrations r  ON r.event_id=e.id AND r.status='registered'
        LEFT JOIN favorite_events fe ON fe.event_id=e.id AND fe.user_id=%s
        WHERE e.status='approved' AND e.date >= CURDATE()
        GROUP BY e.id ORDER BY e.date ASC
    """, (user_id,))
    events = serialize_rows(cursor.fetchall())
    for e in events:
        cap = e.get("capacity") or 0
        reg = e.get("registered_count") or 0
        e["seats_left"] = max(cap - reg, 0)
        e["is_full"]    = reg >= cap
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)


# ── GET EVENT DETAIL ──
def get_event_detail(request, event_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.*, c.name AS club_name,
               COUNT(DISTINCT r.id) AS registered_count,
               AVG(f.rating) AS avg_rating, COUNT(DISTINCT f.id) AS total_reviews
        FROM events e JOIN clubs c ON e.club_id=c.id
        LEFT JOIN registrations r  ON r.event_id=e.id AND r.status='registered'
        LEFT JOIN event_feedback f ON f.event_id=e.id
        WHERE e.id=%s GROUP BY e.id
    """, (event_id,))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)
    event = serialize_row(event)
    event["avg_rating"]    = round(float(event["avg_rating"]), 1) if event.get("avg_rating") else 0
    event["total_reviews"] = event.get("total_reviews") or 0
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.profile_pic
        FROM event_coordinators ec JOIN users u ON ec.user_id=u.id WHERE ec.event_id=%s
    """, (event_id,))
    event["coordinators"] = cursor.fetchall()
    cursor.execute("SELECT image_url FROM event_gallery WHERE event_id=%s", (event_id,))
    event["gallery"] = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse(event)


# ── CREATE EVENT ──
@csrf_exempt
@login_required
def create_event(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data = _json(request)
    required = ["club_id", "title", "date", "time"]
    if not all(data.get(f) for f in required):
        return JsonResponse({"message": "Missing required fields"}, status=400)

    def _int_or_none(val):
        try:
            v = int(val); return v if v > 0 else None
        except (TypeError, ValueError):
            return None

    capacity  = _int_or_none(data.get("capacity"))
    event_cat = data.get("event_category", "individual")
    min_m     = _int_or_none(data.get("min_members"))
    max_m     = _int_or_none(data.get("max_members"))

    if event_cat == "team":
        if not min_m or not max_m:
            return JsonResponse({"message": "Team events require min and max members"}, status=400)
        if min_m < 2 or max_m < min_m:
            return JsonResponse({"message": "Invalid team size: min >= 2, max >= min"}, status=400)

    cursor, conn = get_cursor()
    cursor.execute(
        "SELECT role FROM club_memberships WHERE user_id=%s AND club_id=%s",
        (request.session["user_id"], data.get("club_id"))
    )
    membership = cursor.fetchone()
    if not membership:
        close_connection(cursor, conn)
        return JsonResponse({"message": "You are not a member of this club"}, status=403)

    from apps.decorators import can_manage_events, is_president as _chk_president
    if not can_manage_events(membership["role"]):
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only event management roles can create events"}, status=403)

    is_pres        = _chk_president(membership["role"])
    initial_status = "pending_admin" if is_pres else "pending_president"
    pres_approved  = True if is_pres else False
    event_code     = str(uuid.uuid4())[:8]

    cursor.execute("""
        INSERT INTO events (
            club_id, title, description, date, time, location, type, capacity,
            event_category, min_members, max_members, is_paid, price,
            prize_pool, about, rules, instructions, agenda,
            created_by, event_code, president_approved, admin_approved, status
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,%s)
    """, (
        data.get("club_id"), data.get("title"), data.get("description"),
        data.get("date"), data.get("time"), data.get("location"), data.get("type"),
        capacity, event_cat, min_m, max_m,
        bool(data.get("is_paid", False)), data.get("price") or 0,
        data.get("prize_pool"), data.get("about"), data.get("rules"),
        data.get("instructions"), data.get("agenda"),
        request.session["user_id"], event_code, pres_approved, initial_status
    ))
    log_activity(cursor, f"Event created: '{data.get('title')}' by user {request.session['user_id']}")
    conn.commit()
    event_id = cursor.lastrowid
    close_connection(cursor, conn)
    return JsonResponse({
        "message":    "Event created and sent to admin for approval" if is_pres else "Event created",
        "event_code": event_code,
        "event_id":   event_id,
        "is_president": is_pres,
    })


# ── UPDATE EVENT ──
@csrf_exempt
@login_required
def update_event(request, event_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data = _json(request)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.created_by, e.club_id, cm.role FROM events e
        LEFT JOIN club_memberships cm ON cm.club_id=e.club_id AND cm.user_id=%s
        WHERE e.id=%s
    """, (request.session["user_id"], event_id))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)

    is_creator   = event["created_by"] == request.session["user_id"]
    role         = event["role"] or ""
    is_president = role == "president"
    is_vp        = role == "vice_president"

    if not is_creator and not is_president and not is_vp:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Not authorized to update this event"}, status=403)

    if is_vp and not is_creator:
        cursor.execute("""
            INSERT INTO pending_changes (club_id, changed_by, change_type, target_id, payload)
            VALUES (%s,%s,'event_edit',%s,%s)
        """, (event["club_id"], request.session["user_id"], event_id, json.dumps(data)))
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Edit submitted for president approval"})

    cursor.execute("""
        UPDATE events SET title=%s, description=%s, date=%s, time=%s,
            location=%s, type=%s, capacity=%s, event_category=%s,
            min_members=%s, max_members=%s, is_paid=%s, price=%s,
            prize_pool=%s, about=%s, rules=%s, instructions=%s, agenda=%s
        WHERE id=%s
    """, (
        data.get("title"), data.get("description"), data.get("date"), data.get("time"),
        data.get("location"), data.get("type"), data.get("capacity"),
        data.get("event_category", "individual"),
        data.get("min_members") or None, data.get("max_members") or None,
        bool(data.get("is_paid", False)), data.get("price") or 0,
        data.get("prize_pool"), data.get("about"), data.get("rules"),
        data.get("instructions"), data.get("agenda"), event_id
    ))
    log_activity(cursor, f"Event {event_id} updated by user {request.session['user_id']}")
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Event updated"})


# ── DELETE EVENT ──
@csrf_exempt
@login_required
def delete_event(request, event_id):
    if request.method != "DELETE":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.created_by, e.club_id, cm.role FROM events e
        LEFT JOIN club_memberships cm ON cm.club_id=e.club_id AND cm.user_id=%s
        WHERE e.id=%s
    """, (request.session["user_id"], event_id))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)
    is_creator   = event["created_by"] == request.session["user_id"]
    is_president = (event["role"] or "") == "president"
    if not is_creator and not is_president:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Not authorized to delete this event"}, status=403)
    cursor.execute("DELETE FROM events WHERE id=%s", (event_id,))
    log_activity(cursor, f"Event {event_id} deleted by user {request.session['user_id']}")
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Event deleted"})


# ── CANCEL EVENT ──
@csrf_exempt
@login_required
def cancel_event(request, event_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.created_by, e.club_id, e.title, cm.role FROM events e
        LEFT JOIN club_memberships cm ON cm.club_id=e.club_id AND cm.user_id=%s
        WHERE e.id=%s
    """, (request.session["user_id"], event_id))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)
    cursor.execute("UPDATE events SET status='cancelled' WHERE id=%s", (event_id,))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Event cancelled"})


# ── GET GALLERY ──
def get_event_gallery(request, event_id):
    cursor, conn = get_cursor()
    cursor.execute("SELECT id, image_url FROM event_gallery WHERE event_id=%s ORDER BY id ASC", (event_id,))
    images = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse(images, safe=False)


# ── UPLOAD GALLERY IMAGE ──
@csrf_exempt
@login_required
def upload_gallery_image(request, event_id):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    image = request.FILES.get("image")
    if not image or not _allowed(image.name):
        return JsonResponse({"message": "Invalid image"}, status=400)
    filename  = str(uuid.uuid4()) + "_" + image.name
    path      = os.path.join(djsettings.MEDIA_ROOT, "uploads", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb+") as f:
        for chunk in image.chunks():
            f.write(chunk)
    image_url = f"uploads/{filename}"
    cursor, conn = get_cursor()
    cursor.execute("INSERT INTO event_gallery(event_id, image_url) VALUES(%s,%s)", (event_id, image_url))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Image uploaded", "image_url": image_url})


# ── DELETE GALLERY IMAGE ──
@csrf_exempt
@login_required
def delete_gallery_image(request, event_id, image_id):
    if request.method != "DELETE":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("SELECT created_by, club_id FROM events WHERE id=%s", (event_id,))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)
    cursor.execute("SELECT role FROM club_memberships WHERE user_id=%s AND club_id=%s", (user_id, event["club_id"]))
    mem = cursor.fetchone()
    cursor.execute("SELECT id FROM event_coordinators WHERE event_id=%s AND user_id=%s", (event_id, user_id))
    is_coord     = cursor.fetchone() is not None
    is_creator   = event["created_by"] == user_id
    role         = mem["role"] if mem else ""
    is_admin     = request.session.get("role") == "admin"
    is_leadership = role in ("president", "vice_president")
    from apps.decorators import can_manage_events
    if not (is_creator or is_coord or is_leadership or is_admin or can_manage_events(role)):
        close_connection(cursor, conn)
        return JsonResponse({"message": "Not authorized"}, status=403)
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


# ── GET / SUBMIT FEEDBACK ──
def get_event_feedback(request, event_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT u.name, f.rating, f.comment, f.created_at FROM event_feedback f
        JOIN users u ON u.id=f.user_id WHERE f.event_id=%s ORDER BY f.created_at DESC
    """, (event_id,))
    feedback = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(feedback, safe=False)

@csrf_exempt
@login_required
def submit_feedback(request, event_id):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data    = _json(request)
    rating  = data.get("rating")
    comment = data.get("comment")
    if not rating:
        return JsonResponse({"message": "Rating required"}, status=400)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT id FROM registrations WHERE user_id=%s AND event_id=%s AND status='registered'
    """, (request.session["user_id"], event_id))
    if not cursor.fetchone():
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only participants can submit feedback"}, status=403)
    cursor.execute("""
        INSERT INTO event_feedback(event_id, user_id, rating, comment) VALUES(%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE rating=%s, comment=%s
    """, (event_id, request.session["user_id"], rating, comment, rating, comment))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Feedback submitted"})


# ── TOGGLE FAVOURITE EVENT ──
@csrf_exempt
@login_required
def toggle_favourite_event(request, event_id):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    if request.method == "POST":
        cursor.execute("INSERT IGNORE INTO favorite_events(user_id,event_id) VALUES(%s,%s)", (user_id, event_id))
        message = "favorited"
    elif request.method == "DELETE":
        cursor.execute("DELETE FROM favorite_events WHERE user_id=%s AND event_id=%s", (user_id, event_id))
        message = "unfavorited"
    else:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Method not allowed"}, status=405)
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": message})


# ── POPULAR & FAVOURITED EVENTS ──
def popular_events(request):
    user_id = request.session.get("user_id")
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.*, c.name AS club_name, COUNT(DISTINCT r.id) AS registered_count,
               CASE WHEN fe.user_id IS NULL THEN FALSE ELSE TRUE END AS is_favorited
        FROM events e JOIN clubs c ON e.club_id=c.id
        LEFT JOIN registrations r  ON r.event_id=e.id AND r.status='registered'
        LEFT JOIN favorite_events fe ON fe.event_id=e.id AND fe.user_id=%s
        WHERE e.status='approved'
        GROUP BY e.id ORDER BY registered_count DESC LIMIT 20
    """, (user_id,))
    events = serialize_rows(cursor.fetchall())
    for e in events:
        cap = e.get("capacity") or 0; reg = e.get("registered_count") or 0
        e["seats_left"] = max(cap - reg, 0); e["is_full"] = reg >= cap
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)

def favourited_events(request):
    user_id = request.session.get("user_id")
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.*, c.name AS club_name, COUNT(DISTINCT r.id) AS registered_count,
               COUNT(DISTINCT fe2.id) AS favorite_count,
               CASE WHEN fe.user_id IS NULL THEN FALSE ELSE TRUE END AS is_favorited
        FROM events e JOIN clubs c ON e.club_id=c.id
        LEFT JOIN registrations r   ON r.event_id=e.id AND r.status='registered'
        LEFT JOIN favorite_events fe  ON fe.event_id=e.id AND fe.user_id=%s
        LEFT JOIN favorite_events fe2 ON fe2.event_id=e.id
        WHERE e.status='approved'
        GROUP BY e.id ORDER BY favorite_count DESC LIMIT 20
    """, (user_id,))
    events = serialize_rows(cursor.fetchall())
    for e in events:
        cap = e.get("capacity") or 0; reg = e.get("registered_count") or 0
        e["seats_left"] = max(cap - reg, 0); e["is_full"] = reg >= cap
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)


# ── UPCOMING EVENTS ──
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


# ── CHECK EVENT CONFLICT ──
@csrf_exempt
@login_required
def check_event_conflict(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data       = _json(request)
    venue      = data.get("location", "").strip()
    date       = data.get("date")
    time       = data.get("time")
    exclude_id = data.get("exclude_id")
    if not venue or not date or not time:
        return JsonResponse({"conflict": False})
    cursor, conn = get_cursor()
    query  = """
        SELECT id, title, date, time, location, club_id FROM events
        WHERE LOWER(TRIM(location))=LOWER(TRIM(%s)) AND date=%s
        AND status NOT IN ('rejected','cancelled')
    """
    params = [venue, date]
    if exclude_id:
        query += " AND id != %s"; params.append(exclude_id)
    cursor.execute(query, params)
    conflicts        = cursor.fetchall()
    actual_conflicts = []
    for c in conflicts:
        event_time = datetime.strptime(str(c["time"])[:5], "%H:%M")
        new_time   = datetime.strptime(time[:5], "%H:%M")
        if abs((event_time - new_time).total_seconds()) / 3600 < 2:
            c["date"] = c["date"].strftime("%Y-%m-%d")
            c["time"] = str(c["time"])[:5]
            actual_conflicts.append(c)
    close_connection(cursor, conn)
    return JsonResponse({"conflict": len(actual_conflicts) > 0, "conflicts": actual_conflicts})


# ── EXPORT REGISTRATIONS TO EXCEL ──
@login_required
def export_registrations(request, event_id):
    try:
        import pandas as pd
        from openpyxl.styles import PatternFill, Font, Alignment
    except ImportError:
        return JsonResponse({"message": "pandas not installed"}, status=500)
    cursor, conn = get_cursor()
    cursor.execute("SELECT title FROM events WHERE id=%s", (event_id,))
    event = cursor.fetchone()
    cursor.execute("""
        SELECT
            u.name                                                      AS Name,
            u.reg_no                                                    AS `Reg No`,
            u.email                                                     AS Email,
            u.department                                                AS Department,
            u.year                                                      AS Year,
            r.registered_at                                             AS `Registered At`,
            CASE WHEN a.user_id IS NOT NULL THEN 'Yes' ELSE 'No' END  AS Attended
        FROM registrations r
        JOIN users u ON r.user_id = u.id
        LEFT JOIN event_attendance a
            ON a.event_id = r.event_id AND a.user_id = r.user_id
        WHERE r.event_id = %s AND r.status = 'registered'
        ORDER BY u.name ASC
    """, (event_id,))
    rows = cursor.fetchall()
    close_connection(cursor, conn)
    df     = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Registrations")
        ws = writer.sheets["Registrations"]
        header_fill  = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
        header_font  = Font(color="FFFFFF", bold=True)
        center_align = Alignment(horizontal="center", vertical="center")
        for cell in ws[1]:
            cell.fill      = header_fill
            cell.font      = header_font
            cell.alignment = center_align
        attended_col = None
        for idx, cell in enumerate(ws[1], 1):
            if cell.value == "Attended":
                attended_col = idx
                break
        if attended_col:
            green      = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
            red        = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
            green_font = Font(color="065F46", bold=True)
            red_font   = Font(color="991B1B", bold=True)
            for row in ws.iter_rows(min_row=2):
                cell = row[attended_col - 1]
                if cell.value == "Yes":
                    cell.fill = green; cell.font = green_font
                else:
                    cell.fill = red;   cell.font = red_font
                cell.alignment = center_align
        for col in ws.columns:
            max_len = max((len(str(c.value)) if c.value else 0) for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)
    output.seek(0)
    safe_title = (event["title"] if event else f"event_{event_id}").replace(" ", "_")
    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{safe_title}_registrations.xlsx"'
    return response


# ── WAITLIST ──
@csrf_exempt
@login_required
def waitlist(request, event_id):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    if request.method == "POST":
        cursor.execute("SELECT capacity FROM events WHERE id=%s", (event_id,))
        event = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS total FROM registrations WHERE event_id=%s AND status='registered'", (event_id,))
        count = cursor.fetchone()["total"]
        if event["capacity"] and count < event["capacity"]:
            close_connection(cursor, conn)
            return JsonResponse({"message": "Event is not full yet. You can register directly."}, status=400)
        try:
            cursor.execute("INSERT INTO event_waitlist(event_id, user_id) VALUES(%s,%s)", (event_id, user_id))
            conn.commit()
        except Exception:
            close_connection(cursor, conn)
            return JsonResponse({"message": "Already on waitlist"}, status=400)
        close_connection(cursor, conn)
        return JsonResponse({"message": "Added to waitlist"})
    elif request.method == "DELETE":
        cursor.execute("DELETE FROM event_waitlist WHERE event_id=%s AND user_id=%s", (event_id, user_id))
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Removed from waitlist"})
    return JsonResponse({"message": "Method not allowed"}, status=405)


# ── WAITLIST STATUS ──
@login_required
def waitlist_status(request, event_id):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("SELECT id FROM event_waitlist WHERE event_id=%s AND user_id=%s", (event_id, user_id))
    on_waitlist = cursor.fetchone() is not None
    position    = None
    if on_waitlist:
        cursor.execute("""
            SELECT COUNT(*) AS pos FROM event_waitlist WHERE event_id=%s
            AND created_at <= (SELECT created_at FROM event_waitlist WHERE event_id=%s AND user_id=%s)
        """, (event_id, event_id, user_id))
        pos_row  = cursor.fetchone()
        position = pos_row["pos"] if pos_row else None
    cursor.execute("SELECT COUNT(*) AS total FROM event_waitlist WHERE event_id=%s", (event_id,))
    total = cursor.fetchone()["total"]
    close_connection(cursor, conn)
    return JsonResponse({"on_waitlist": on_waitlist, "position": position, "total_waiting": total})


# ── GET COORDINATORS ──
@login_required
def get_coordinators(request, event_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.phone, u.profile_pic, cm.role AS club_role
        FROM event_coordinators ec JOIN users u ON ec.user_id=u.id
        JOIN events e ON ec.event_id=e.id
        LEFT JOIN club_memberships cm ON cm.user_id=u.id AND cm.club_id=e.club_id
        WHERE ec.event_id=%s
    """, (event_id,))
    coordinators = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse(coordinators, safe=False)


# ── ASSIGN COORDINATOR ──
@csrf_exempt
@login_required
def assign_coordinator(request, event_id):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data    = _json(request)
    user_id = data.get("user_id")
    cursor, conn = get_cursor()
    cursor.execute("SELECT club_id FROM events WHERE id=%s", (event_id,))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)
    cursor.execute("SELECT id FROM club_memberships WHERE user_id=%s AND club_id=%s", (user_id, event["club_id"]))
    if not cursor.fetchone():
        close_connection(cursor, conn)
        return JsonResponse({"message": "User is not a member of this club"}, status=403)
    try:
        cursor.execute("INSERT INTO event_coordinators(event_id, user_id) VALUES(%s,%s)", (event_id, user_id))
        conn.commit()
    except Exception:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Already coordinator"}, status=400)
    close_connection(cursor, conn)
    return JsonResponse({"message": "Coordinator assigned"})


# ── CLUB EVENTS ──
@login_required
def club_events(request, club_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.*, COUNT(r.id) AS registered_count FROM events e
        LEFT JOIN registrations r ON r.event_id=e.id
        WHERE e.club_id=%s GROUP BY e.id ORDER BY e.date ASC
    """, (club_id,))
    events = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)


# ── CLUB STATS ──
@login_required
def club_stats(request, club_id):
    cursor, conn = get_cursor()
    cursor.execute("SELECT COUNT(*) AS c FROM events WHERE club_id=%s", (club_id,))
    total = cursor.fetchone()["c"]
    cursor.execute("SELECT COUNT(*) AS c FROM events WHERE club_id=%s AND date >= CURDATE()", (club_id,))
    upcoming = cursor.fetchone()["c"]
    cursor.execute("""
        SELECT COUNT(*) AS c FROM registrations r JOIN events e ON r.event_id=e.id WHERE e.club_id=%s
    """, (club_id,))
    registrations = cursor.fetchone()["c"]
    close_connection(cursor, conn)
    return JsonResponse({"events": total, "upcoming": upcoming, "registrations": registrations})


# ── ADD MEMBER (admin) ──
@csrf_exempt
@login_required
def add_member(request, club_id):
    from apps.decorators import admin_required as _ar
    if request.session.get("role") != "admin":
        return JsonResponse({"message": "Admin access required"}, status=403)
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data    = _json(request)
    user_id = data.get("user_id")
    role    = data.get("role", "event_coordinator")
    if not user_id:
        return JsonResponse({"message": "user_id required"}, status=400)
    cursor, conn = get_cursor()
    try:
        cursor.execute(
            "INSERT INTO club_memberships(user_id, club_id, role) VALUES(%s,%s,%s)",
            (user_id, club_id, role)
        )
        log_activity(cursor, f"User {user_id} added to club {club_id} with role '{role}'")
        conn.commit()
    except Exception:
        close_connection(cursor, conn)
        return JsonResponse({"message": "User already in this club"}, status=400)
    close_connection(cursor, conn)
    return JsonResponse({"message": "Member added"})


# ── GALLERY FULL (with IDs for deletion) ──
@login_required
def get_event_gallery_full(request, event_id):
    cursor, conn = get_cursor()
    cursor.execute("SELECT id, image_url FROM event_gallery WHERE event_id=%s ORDER BY id ASC", (event_id,))
    images = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse(images, safe=False)


# ── EVENT REGISTRATIONS LIST ──
@login_required
def event_registrations_list(request, event_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT u.name, u.email, u.department, u.year FROM registrations r
        JOIN users u ON r.user_id=u.id
        WHERE r.event_id=%s AND r.status='registered' ORDER BY u.name
    """, (event_id,))
    students = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse(students, safe=False)


# ── REMOVE COORDINATOR ──
@csrf_exempt
@login_required
def remove_coordinator(request, event_id, user_id):
    if request.method != "DELETE":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT cm.role FROM events e
        JOIN club_memberships cm ON cm.club_id=e.club_id AND cm.user_id=%s
        WHERE e.id=%s
    """, (request.session["user_id"], event_id))
    role = cursor.fetchone()
    if not role or role["role"] not in ("president", "vice_president", "admin"):
        if request.session.get("role") != "admin":
            close_connection(cursor, conn)
            return JsonResponse({"message": "Only president can remove coordinators"}, status=403)
    cursor.execute("DELETE FROM event_coordinators WHERE event_id=%s AND user_id=%s", (event_id, user_id))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Coordinator removed"})


# ── PRESIDENT APPROVE EVENT ──
@csrf_exempt
@login_required
def president_approve_event(request, event_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT cm.role FROM events e
        JOIN club_memberships cm ON cm.club_id=e.club_id AND cm.user_id=%s WHERE e.id=%s
    """, (request.session["user_id"], event_id))
    role = cursor.fetchone()
    if not role or role["role"] != "president":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only president can approve"}, status=403)
    cursor.execute("UPDATE events SET president_approved=TRUE, status='pending_admin' WHERE id=%s AND status='pending_president'", (event_id,))
    log_activity(cursor, f"Event {event_id} approved by president {request.session['user_id']}")
    conn.commit()
    cursor.execute("""
        SELECT e.title, u.name, u.email, p.name AS president_name
        FROM events e JOIN users u ON e.created_by=u.id JOIN users p ON p.id=%s WHERE e.id=%s
    """, (request.session["user_id"], event_id))
    info = cursor.fetchone()
    close_connection(cursor, conn)
    if info:
        from apps.email_service import send_event_approval_email
        try:
            send_event_approval_email(info["email"], info["name"], info["title"], f"President {info['president_name']}")
        except Exception:
            pass
    return JsonResponse({"message": "Event approved by president"})


# ── PRESIDENT REJECT EVENT ──
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
    cursor.execute("""
        SELECT e.title, u.name, u.email, p.name AS president_name
        FROM events e JOIN users u ON e.created_by=u.id JOIN users p ON p.id=%s WHERE e.id=%s
    """, (request.session["user_id"], event_id))
    info = cursor.fetchone()
    close_connection(cursor, conn)
    if info:
        from apps.email_service import send_event_rejection_email
        try:
            send_event_rejection_email(info["email"], info["name"], info["title"], f"President {info['president_name']}", reason)
        except Exception:
            pass
    return JsonResponse({"message": "Event rejected by president"})


# ── GET PENDING EVENTS ──
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
import json
import uuid
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings as djsettings
from apps.db import get_cursor, close_connection, serialize_rows, log_activity
from apps.decorators import login_required

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

def _json(request):
    try: return json.loads(request.body)
    except: return {}

def _get_role(user_id, club_id, cursor):
    cursor.execute("SELECT role FROM club_memberships WHERE user_id=%s AND club_id=%s", (user_id, club_id))
    row = cursor.fetchone()
    return row["role"] if row else None


@login_required
def my_manageable_events(request, club_id):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    role = _get_role(user_id, club_id, cursor)
    if not role:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Not a member of this club"}, status=403)
    from apps.decorators import can_manage_events, is_leadership
    if not can_manage_events(role):
        close_connection(cursor, conn)
        return JsonResponse({"message": "No event management access"}, status=403)
    if is_leadership(role):
        cursor.execute("""
            SELECT e.*, COUNT(r.id) AS registered_count FROM events e
            LEFT JOIN registrations r ON r.event_id=e.id
            WHERE e.club_id=%s GROUP BY e.id ORDER BY e.date DESC
        """, (club_id,))
    else:
        cursor.execute("""
            SELECT DISTINCT e.*, COUNT(r.id) AS registered_count FROM events e
            LEFT JOIN registrations r ON r.event_id=e.id
            LEFT JOIN event_coordinators ec ON ec.event_id=e.id
            WHERE e.club_id=%s AND (e.created_by=%s OR ec.user_id=%s)
            GROUP BY e.id ORDER BY e.date DESC
        """, (club_id, user_id, user_id))
    events = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)


@csrf_exempt
@login_required
def member_edit_event(request, club_id, event_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    user_id = request.session["user_id"]
    data    = _json(request)
    cursor, conn = get_cursor()
    role = _get_role(user_id, club_id, cursor)
    if not role:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Not a member of this club"}, status=403)
    from apps.decorators import can_manage_events
    if not can_manage_events(role):
        close_connection(cursor, conn)
        return JsonResponse({"message": "No event management access"}, status=403)
    cursor.execute("SELECT created_by FROM events WHERE id=%s AND club_id=%s", (event_id, club_id))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)
    is_creator     = event["created_by"] == user_id
    cursor.execute("SELECT id FROM event_coordinators WHERE event_id=%s AND user_id=%s", (event_id, user_id))
    is_coordinator = cursor.fetchone() is not None
    is_leadership  = role in ("president", "vice_president")
    if not is_creator and not is_coordinator and not is_leadership:
        close_connection(cursor, conn)
        return JsonResponse({"message": "You can only edit events you created or coordinate"}, status=403)
    if role == "vice_president" and not is_creator:
        cursor.execute("""
            INSERT INTO pending_changes(club_id, changed_by, change_type, target_id, payload)
            VALUES(%s,%s,'event_edit',%s,%s)
        """, (club_id, user_id, event_id, json.dumps(data)))
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Edit submitted for president approval"})
    if data.get("capacity"):
        cursor.execute("SELECT COUNT(*) AS total FROM registrations WHERE event_id=%s AND status='registered'", (event_id,))
        reg_count = cursor.fetchone()["total"]
        if int(data["capacity"]) < reg_count:
            close_connection(cursor, conn)
            return JsonResponse({"message": f"Capacity cannot be less than current registrations ({reg_count})"}, status=400)
    cursor.execute("""
        UPDATE events SET description=%s, location=%s, date=%s, time=%s,
            type=%s, capacity=%s, prize_pool=%s, about=%s, rules=%s, instructions=%s
        WHERE id=%s AND club_id=%s
    """, (data.get("description"), data.get("location"), data.get("date"), data.get("time"),
          data.get("type"), data.get("capacity") or None,
          data.get("prize_pool"), data.get("about"), data.get("rules"), data.get("instructions"),
          event_id, club_id))
    log_activity(cursor, f"Event {event_id} updated by user {user_id} in club {club_id}")
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Event updated"})


@csrf_exempt
@login_required
def vp_request_event_delete(request, club_id, event_id):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    role = _get_role(user_id, club_id, cursor)
    if role != "vice_president":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only VP can submit a deletion request"}, status=403)
    cursor.execute("SELECT id, title FROM events WHERE id=%s AND club_id=%s", (event_id, club_id))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found in this club"}, status=404)
    cursor.execute("""
        INSERT INTO pending_changes(club_id, changed_by, change_type, target_id, payload)
        VALUES(%s,%s,'event_delete',%s,%s)
    """, (club_id, user_id, event_id, json.dumps({"title": event["title"]})))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": f"Deletion request for '{event['title']}' submitted."})


# ════════════════════════════════════════════════════════════
# QR ATTENDANCE SYSTEM
# Layer 1: Rotating HMAC token (changes every 30s) — screenshot useless after 30s
# Layer 2: One scan per student per event — UNIQUE(event_id, user_id) in DB
# Layer 3: 10-minute session expiry from when coordinator clicks Generate
# ════════════════════════════════════════════════════════════

import hmac
import hashlib
import time
import secrets

def _make_token(seed, event_id):
    """
    Generate rotating HMAC token.
    Changes every 30 seconds — even if a student screenshots it,
    it expires in at most 30 seconds.
    """
    window = int(time.time()) // 30  # changes every 30 seconds
    msg    = f"{event_id}:{window}:{seed}".encode()
    return hmac.new(seed.encode(), msg, hashlib.sha256).hexdigest()[:16]


def _verify_token(seed, event_id, token):
    """
    Accept current window AND previous window (±30s tolerance).
    Prevents edge-case failures if student scans right as token rotates.
    """
    window = int(time.time()) // 30
    for w in [window, window - 1, window + 1]:
        msg  = f"{event_id}:{w}:{seed}".encode()
        expected = hmac.new(seed.encode(), msg, hashlib.sha256).hexdigest()[:16]
        if hmac.compare_digest(expected, token):
            return True
    return False


@csrf_exempt
@login_required
def generate_qr_session(request, event_id):
    """
    Coordinator clicks 'Generate QR'.
    Creates a QR session with 10-minute expiry.
    Returns the seed so frontend can compute rotating tokens.
    """
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)

    user_id = request.session["user_id"]
    cursor, conn = get_cursor()

    # Verify user is coordinator or club member with event management role
    cursor.execute("""
        SELECT e.club_id FROM events e WHERE e.id = %s
    """, (event_id,))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)

    # Check if user is a coordinator OR has event management role in this club
    cursor.execute("""
        SELECT id FROM event_coordinators WHERE event_id=%s AND user_id=%s
    """, (event_id, user_id))
    is_coord = cursor.fetchone() is not None

    cursor.execute("""
        SELECT role FROM club_memberships WHERE club_id=%s AND user_id=%s
    """, (event["club_id"], user_id))
    membership = cursor.fetchone()

    from apps.decorators import can_manage_events
    is_manager = membership and can_manage_events(membership["role"])
    is_admin   = request.session.get("role") == "admin"

    if not (is_coord or is_manager or is_admin):
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only event coordinators can generate QR codes"}, status=403)

    # Generate new seed — random each time coordinator clicks Generate
    seed       = secrets.token_hex(16)
    expires_at = datetime.now() + timedelta(minutes=10)

    # Upsert — replace any existing session for this event
    cursor.execute("""
        INSERT INTO qr_sessions (event_id, seed, generated_by, generated_at, expires_at, is_active)
        VALUES (%s, %s, %s, NOW(), %s, TRUE)
        ON DUPLICATE KEY UPDATE
            seed         = VALUES(seed),
            generated_by = VALUES(generated_by),
            generated_at = NOW(),
            expires_at   = VALUES(expires_at),
            is_active    = TRUE
    """, (event_id, seed, user_id, expires_at.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    close_connection(cursor, conn)

    return JsonResponse({
        "seed":       seed,
        "event_id":   event_id,
        "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        "expires_in": 600,  # seconds
        "token_ttl":  30,   # seconds per token rotation
    })


@login_required
def get_qr_token(request, event_id):
    """
    Called by coordinator's screen every 30s to get the current token.
    Frontend builds QR from: event_id + token
    """
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT seed, expires_at FROM qr_sessions
        WHERE event_id=%s AND is_active=TRUE AND expires_at > NOW()
    """, (event_id,))
    session = cursor.fetchone()
    close_connection(cursor, conn)

    if not session:
        return JsonResponse({"message": "No active QR session. Generate a new one."}, status=404)

    token      = _make_token(session["seed"], event_id)
    expires_at = session["expires_at"]
    if hasattr(expires_at, "strftime"):
        expires_at = expires_at.strftime("%Y-%m-%d %H:%M:%S")

    now        = datetime.now()
    remaining  = int((datetime.strptime(str(expires_at)[:19], "%Y-%m-%d %H:%M:%S") - now).total_seconds())

    return JsonResponse({
        "token":      token,
        "event_id":   event_id,
        "expires_at": expires_at,
        "remaining":  max(0, remaining),
        "qr_data":    f"RECQR:{event_id}:{token}",
    })


@csrf_exempt
@login_required
def mark_attendance(request, event_id):
    """
    Student scans QR and their phone calls this endpoint.
    Layer 1: Validates rotating HMAC token
    Layer 2: Checks student is registered
    Layer 3: UNIQUE constraint prevents double attendance
    """
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)

    data    = _json(request)
    token   = data.get("token", "").strip()
    user_id = request.session["user_id"]

    if not token:
        return JsonResponse({"message": "Token required"}, status=400)

    cursor, conn = get_cursor()

    # Get active QR session
    cursor.execute("""
        SELECT seed, expires_at FROM qr_sessions
        WHERE event_id=%s AND is_active=TRUE AND expires_at > NOW()
    """, (event_id,))
    qr_session = cursor.fetchone()

    if not qr_session:
        close_connection(cursor, conn)
        return JsonResponse({
            "success": False,
            "message": "QR code has expired. Ask the coordinator to generate a new one."
        }, status=400)

    # Layer 1: Verify rotating token
    if not _verify_token(qr_session["seed"], event_id, token):
        close_connection(cursor, conn)
        return JsonResponse({
            "success": False,
            "message": "Invalid or expired QR code. Please scan the current QR shown by the coordinator."
        }, status=400)

    # Check student is registered for the event
    cursor.execute("""
        SELECT id FROM registrations
        WHERE user_id=%s AND event_id=%s AND status='registered'
    """, (user_id, event_id))
    if not cursor.fetchone():
        close_connection(cursor, conn)
        return JsonResponse({
            "success": False,
            "message": "You are not registered for this event."
        }, status=403)

    # Layer 2: Mark attendance — UNIQUE constraint prevents duplicates
    try:
        cursor.execute("""
            INSERT INTO event_attendance (event_id, user_id)
            VALUES (%s, %s)
        """, (event_id, user_id))
        conn.commit()
        cursor.execute("SELECT name FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()
        close_connection(cursor, conn)
        return JsonResponse({
            "success": True,
            "message": f"✅ Attendance marked for {user['name'] if user else 'you'}!"
        })
    except Exception:
        close_connection(cursor, conn)
        return JsonResponse({
            "success": False,
            "message": "Attendance already marked for this event."
        }, status=400)


@login_required
def get_attendance_list(request, event_id):
    """Returns list of students who have marked attendance."""
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT u.name, u.reg_no, u.email, u.department, u.year,
               a.marked_at
        FROM event_attendance a
        JOIN users u ON a.user_id = u.id
        WHERE a.event_id = %s
        ORDER BY a.marked_at ASC
    """, (event_id,))
    attendance = serialize_rows(cursor.fetchall())

    cursor.execute("""
        SELECT COUNT(*) AS total FROM registrations
        WHERE event_id=%s AND status='registered'
    """, (event_id,))
    total_registered = cursor.fetchone()["total"]

    close_connection(cursor, conn)
    return JsonResponse({
        "attendance":       attendance,
        "attended":         len(attendance),
        "total_registered": total_registered,
    })

@login_required
def my_attendance_status(request, event_id):
    """Check if the current user has marked attendance for this event."""
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute(
        "SELECT marked_at FROM event_attendance WHERE event_id=%s AND user_id=%s",
        (event_id, user_id)
    )
    row = cursor.fetchone()
    close_connection(cursor, conn)
    if row:
        marked_at = row["marked_at"]
        if hasattr(marked_at, "strftime"):
            marked_at = marked_at.strftime("%Y-%m-%d %H:%M")
        return JsonResponse({"attended": True, "marked_at": marked_at})
    return JsonResponse({"attended": False})
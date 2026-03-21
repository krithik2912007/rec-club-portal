import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from apps.db import get_cursor, close_connection, serialize_row, serialize_rows, log_activity
from apps.decorators import login_required, admin_required


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


# ── GET ALL CLUBS ──
def get_clubs(request):
    user_id = request.session.get("user_id")
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT c.*, COUNT(e.id) AS event_count,
               CASE WHEN fc.user_id IS NULL THEN FALSE ELSE TRUE END AS is_favorited
        FROM clubs c
        LEFT JOIN events e  ON e.club_id = c.id AND e.status = 'approved'
        LEFT JOIN favorite_clubs fc ON fc.club_id = c.id AND fc.user_id = %s
        GROUP BY c.id ORDER BY c.name ASC
    """, (user_id,))
    clubs = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(clubs, safe=False)


# ── GET CLUB DETAIL ──
def get_club_detail(request, club_id):
    cursor, conn = get_cursor()
    cursor.execute("SELECT * FROM clubs WHERE id=%s", (club_id,))
    club = cursor.fetchone()
    if not club:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Club not found"}, status=404)

    cursor.execute("""
        SELECT e.*, COUNT(DISTINCT r.id) AS registered_count,
               AVG(f.rating) AS avg_rating, COUNT(DISTINCT f.id) AS total_reviews
        FROM events e
        LEFT JOIN registrations r ON r.event_id=e.id
        LEFT JOIN event_feedback f ON f.event_id=e.id
        WHERE e.club_id=%s AND e.status='approved'
        GROUP BY e.id ORDER BY e.date ASC
    """, (club_id,))
    events = serialize_rows(cursor.fetchall())
    for e in events:
        e["avg_rating"]    = round(float(e["avg_rating"]), 1) if e.get("avg_rating") else 0
        e["total_reviews"] = e.get("total_reviews") or 0

    cursor.execute("""
        SELECT u.id, u.name, cm.role FROM club_memberships cm
        JOIN users u ON cm.user_id=u.id
        WHERE cm.club_id=%s ORDER BY cm.role
    """, (club_id,))
    members = serialize_rows(cursor.fetchall())
    club    = serialize_row(club)
    close_connection(cursor, conn)
    return JsonResponse({"club": club, "events": events, "members": members})


# ── FEATURED CLUBS ──
def featured_clubs(request):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT c.*, COUNT(DISTINCT e.id) AS event_count
        FROM clubs c
        LEFT JOIN events e ON e.club_id=c.id AND e.status='approved'
        GROUP BY c.id ORDER BY event_count DESC LIMIT 6
    """)
    clubs = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(clubs, safe=False)


# ── SEARCH CLUBS ──
def search_clubs(request):
    q = request.GET.get("q", "").strip()
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT * FROM clubs WHERE name LIKE %s OR category LIKE %s LIMIT 20
    """, (f"%{q}%", f"%{q}%"))
    clubs = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(clubs, safe=False)


# ── POPULAR CLUBS ──
def popular_clubs(request):
    user_id = request.session.get("user_id")
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT c.*, COUNT(DISTINCT e.id) AS event_count,
               COUNT(DISTINCT r.id) AS total_registrations,
               CASE WHEN fc.user_id IS NULL THEN FALSE ELSE TRUE END AS is_favorited
        FROM clubs c
        LEFT JOIN events e  ON e.club_id=c.id AND e.status='approved'
        LEFT JOIN registrations r ON r.event_id=e.id AND r.status='registered'
        LEFT JOIN favorite_clubs fc ON fc.club_id=c.id AND fc.user_id=%s
        GROUP BY c.id ORDER BY total_registrations DESC
    """, (user_id,))
    clubs = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(clubs, safe=False)


# ── FAVOURITED CLUBS ──
def favourited_clubs(request):
    user_id = request.session.get("user_id")
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT c.*, COUNT(DISTINCT e.id) AS event_count,
               COUNT(DISTINCT fc2.id) AS favorite_count,
               CASE WHEN fc.user_id IS NULL THEN FALSE ELSE TRUE END AS is_favorited
        FROM clubs c
        LEFT JOIN events e   ON e.club_id=c.id AND e.status='approved'
        LEFT JOIN favorite_clubs fc  ON fc.club_id=c.id AND fc.user_id=%s
        LEFT JOIN favorite_clubs fc2 ON fc2.club_id=c.id
        GROUP BY c.id ORDER BY favorite_count DESC
    """, (user_id,))
    clubs = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(clubs, safe=False)


# ── GET CLUB MEMBERS ──
@login_required
def get_club_members(request, club_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.reg_no, u.department, u.year,
               u.phone, u.bio, u.github, u.linkedin, u.instagram, u.profile_pic, cm.role
        FROM club_memberships cm
        JOIN users u ON cm.user_id=u.id
        WHERE cm.club_id=%s
        ORDER BY FIELD(cm.role,'president','vice_president','secretary','joint_secretary',
                       'treasurer','hr','event_management_head','event_management_associate',
                       'pr_head','pr_associate','photography'), u.name ASC
    """, (club_id,))
    members = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(members, safe=False)


# ── TOGGLE FAVOURITE CLUB ──
@csrf_exempt
@login_required
def toggle_favourite_club(request, club_id):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    if request.method == "POST":
        cursor.execute("INSERT IGNORE INTO favorite_clubs(user_id,club_id) VALUES(%s,%s)", (user_id, club_id))
        message = "favorited"
    elif request.method == "DELETE":
        cursor.execute("DELETE FROM favorite_clubs WHERE user_id=%s AND club_id=%s", (user_id, club_id))
        message = "unfavorited"
    else:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Method not allowed"}, status=405)
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": message})


# ── USER FAVOURITE CLUBS ──
@login_required
def user_favourite_clubs(request):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT c.* FROM favorite_clubs fc
        JOIN clubs c ON fc.club_id=c.id
        WHERE fc.user_id=%s
    """, (user_id,))
    clubs = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(clubs, safe=False)


# ── PAST EVENTS GALLERY ──
def club_past_events_gallery(request, club_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.id, e.title, e.date, e.time, e.location, e.type,
               AVG(f.rating) AS avg_rating, COUNT(DISTINCT f.id) AS total_reviews,
               COUNT(DISTINCT r.id) AS registered_count
        FROM events e
        LEFT JOIN event_feedback f ON f.event_id=e.id
        LEFT JOIN registrations r  ON r.event_id=e.id
        WHERE e.club_id=%s AND e.status='approved' AND e.date < CURDATE()
        GROUP BY e.id ORDER BY e.date DESC
    """, (club_id,))
    result = []
    for e in serialize_rows(cursor.fetchall()):
        e["avg_rating"]    = round(float(e["avg_rating"]), 1) if e.get("avg_rating") else 0
        e["total_reviews"] = e.get("total_reviews") or 0
        cursor.execute("SELECT image_url FROM event_gallery WHERE event_id=%s LIMIT 1", (e["id"],))
        thumb = cursor.fetchone()
        e["thumbnail"] = thumb["image_url"] if thumb else None
        result.append(e)
    close_connection(cursor, conn)
    return JsonResponse(result, safe=False)


# ── REJECTED EVENTS (last 24hrs) ──
@login_required
def get_rejected_events(request, club_id):
    cursor, conn = get_cursor()
    cutoff = datetime.now() - timedelta(hours=24)
    cursor.execute("""
        SELECT e.id, e.title, e.date, e.time, e.status,
               e.president_rejection_reason, e.admin_rejection_reason, e.created_at
        FROM events e
        WHERE e.club_id=%s AND e.status='rejected' AND e.created_at >= %s
        ORDER BY e.created_at DESC
    """, (club_id, cutoff))
    events = serialize_rows(cursor.fetchall())
    for e in events:
        rejected_time = datetime.strptime(e["created_at"], "%Y-%m-%d %H:%M")
        expires_at    = rejected_time + timedelta(hours=24)
        remaining     = expires_at - datetime.now()
        hours_left    = max(0, int(remaining.total_seconds() // 3600))
        mins_left     = max(0, int((remaining.total_seconds() % 3600) // 60))
        e["expires_in"] = f"{hours_left}h {mins_left}m"
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
def president_get_members(request, club_id):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    role = _get_role(user_id, club_id, cursor)
    if role not in ("president", "vice_president"):
        close_connection(cursor, conn)
        return JsonResponse({"message": "President/VP access required"}, status=403)
    cursor.execute("""
        SELECT u.id, u.name, u.email, u.reg_no, u.department, u.year,
               u.phone, u.bio, u.github, u.linkedin, u.instagram, u.profile_pic, cm.role
        FROM club_memberships cm JOIN users u ON cm.user_id=u.id
        WHERE cm.club_id=%s
        ORDER BY FIELD(cm.role,'president','vice_president','secretary','joint_secretary',
                       'treasurer','hr','event_coordinator','event_management_head',
                       'event_management_associate','pr_head','pr_associate','photography'),
                 u.name ASC
    """, (club_id,))
    members = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse(members, safe=False)


@csrf_exempt
@login_required
def president_member_detail(request, club_id, user_id):
    my_id = request.session["user_id"]
    cursor, conn = get_cursor()
    my_role = _get_role(my_id, club_id, cursor)
    if my_role not in ("president", "vice_president"):
        close_connection(cursor, conn)
        return JsonResponse({"message": "President/VP access required"}, status=403)

    if request.method == "PUT":
        data     = _json(request)
        new_role = data.get("role")
        if not new_role:
            close_connection(cursor, conn)
            return JsonResponse({"message": "Role required"}, status=400)
        cursor.execute("SELECT role FROM club_memberships WHERE user_id=%s AND club_id=%s", (user_id, club_id))
        target = cursor.fetchone()
        if target and target["role"] == "president" and my_role != "president":
            close_connection(cursor, conn)
            return JsonResponse({"message": "Only president can change another president's role"}, status=403)
        if my_role == "vice_president":
            cursor.execute("""
                INSERT INTO pending_changes(club_id, changed_by, change_type, target_id, payload)
                VALUES(%s,%s,'member_role',%s,%s)
            """, (club_id, my_id, user_id, json.dumps({"new_role": new_role})))
            conn.commit()
            close_connection(cursor, conn)
            return JsonResponse({"message": "Role change submitted for president approval"})
        cursor.execute("UPDATE club_memberships SET role=%s WHERE user_id=%s AND club_id=%s", (new_role, user_id, club_id))
        log_activity(cursor, f"President {my_id} changed user {user_id} role to '{new_role}' in club {club_id}")
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Member role updated"})

    elif request.method == "DELETE":
        if user_id == my_id:
            close_connection(cursor, conn)
            return JsonResponse({"message": "Cannot remove yourself"}, status=400)
        if my_role == "vice_president":
            cursor.execute("""
                INSERT INTO pending_changes(club_id, changed_by, change_type, target_id, payload)
                VALUES(%s,%s,'member_role',%s,%s)
            """, (club_id, my_id, user_id, json.dumps({"action": "remove"})))
            conn.commit()
            close_connection(cursor, conn)
            return JsonResponse({"message": "Removal submitted for president approval"})
        cursor.execute("DELETE FROM club_memberships WHERE user_id=%s AND club_id=%s", (user_id, club_id))
        log_activity(cursor, f"President {my_id} removed user {user_id} from club {club_id}")
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Member removed"})

    close_connection(cursor, conn)
    return JsonResponse({"message": "Method not allowed"}, status=405)


@csrf_exempt
@login_required
def president_update_club(request, club_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    my_id = request.session["user_id"]
    cursor, conn = get_cursor()
    my_role = _get_role(my_id, club_id, cursor)
    if my_role not in ("president", "vice_president"):
        close_connection(cursor, conn)
        return JsonResponse({"message": "President/VP access required"}, status=403)
    name        = request.POST.get("name")
    category    = request.POST.get("category")
    description = request.POST.get("description")
    about       = request.POST.get("about")
    vision      = request.POST.get("vision")
    mission     = request.POST.get("mission")
    payload     = {"name": name, "category": category, "description": description,
                   "about": about, "vision": vision, "mission": mission}
    image      = request.FILES.get("image")
    image_path = None
    if image and image.name.rsplit(".", 1)[-1].lower() in ALLOWED_EXTENSIONS:
        filename   = str(uuid.uuid4()) + "_" + image.name
        path       = os.path.join(djsettings.MEDIA_ROOT, "uploads", filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb+") as f:
            for chunk in image.chunks():
                f.write(chunk)
        image_path = "uploads/" + filename
        payload["image"] = image_path
    if my_role == "vice_president":
        cursor.execute("""
            INSERT INTO pending_changes(club_id, changed_by, change_type, target_id, payload)
            VALUES(%s,%s,'club_details',%s,%s)
        """, (club_id, my_id, club_id, json.dumps(payload)))
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Club details update submitted for president approval"})
    if image_path:
        cursor.execute("UPDATE clubs SET name=%s, category=%s, description=%s, about=%s, vision=%s, mission=%s, image=%s WHERE id=%s",
                       (name, category, description, about, vision, mission, image_path, club_id))
    else:
        cursor.execute("UPDATE clubs SET name=%s, category=%s, description=%s, about=%s, vision=%s, mission=%s WHERE id=%s",
                       (name, category, description, about, vision, mission, club_id))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Club details updated"})


@login_required
def get_pending_changes(request, club_id):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    role = _get_role(user_id, club_id, cursor)
    if role != "president":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only president can view pending changes"}, status=403)
    cursor.execute("""
        SELECT pc.*, u.name AS vp_name FROM pending_changes pc
        JOIN users u ON pc.changed_by=u.id
        WHERE pc.club_id=%s AND pc.status='pending' ORDER BY pc.created_at DESC
    """, (club_id,))
    changes = cursor.fetchall()
    enriched = []
    for ch in changes:
        if ch.get("created_at"):
            ch["created_at"] = ch["created_at"].strftime("%Y-%m-%d %H:%M")
        try:
            ch["payload_parsed"] = json.loads(ch.get("payload") or "{}")
        except Exception:
            ch["payload_parsed"] = {}
        if ch["change_type"] in ("event_edit", "event_delete"):
            cursor.execute("SELECT title FROM events WHERE id=%s", (ch["target_id"],))
            ev = cursor.fetchone()
            ch["target_name"] = ev["title"] if ev else ch["payload_parsed"].get("title", f"Event #{ch['target_id']}")
        elif ch["change_type"] == "member_role":
            cursor.execute("SELECT name FROM users WHERE id=%s", (ch["target_id"],))
            mem = cursor.fetchone()
            ch["target_name"] = mem["name"] if mem else f"User #{ch['target_id']}"
        else:
            ch["target_name"] = ""
        enriched.append(ch)
    close_connection(cursor, conn)
    return JsonResponse(enriched, safe=False)


@csrf_exempt
@login_required
def approve_pending_change(request, club_id, change_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    role = _get_role(user_id, club_id, cursor)
    if role != "president":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only president can approve changes"}, status=403)
    cursor.execute("SELECT * FROM pending_changes WHERE id=%s AND club_id=%s AND status='pending'", (change_id, club_id))
    change = cursor.fetchone()
    if not change:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Change not found"}, status=404)
    payload = json.loads(change["payload"])
    if change["change_type"] == "event_edit":
        d = payload
        cursor.execute("""
            UPDATE events SET title=%s, description=%s, date=%s, time=%s, location=%s, type=%s,
                capacity=%s, event_category=%s, min_members=%s, max_members=%s, is_paid=%s, price=%s,
                prize_pool=%s, about=%s, rules=%s, instructions=%s, agenda=%s WHERE id=%s
        """, (d.get("title"), d.get("description"), d.get("date"), d.get("time"), d.get("location"),
              d.get("type"), d.get("capacity"), d.get("event_category","individual"),
              d.get("min_members") or None, d.get("max_members") or None,
              bool(d.get("is_paid",False)), d.get("price") or 0,
              d.get("prize_pool"), d.get("about"), d.get("rules"), d.get("instructions"), d.get("agenda"),
              change["target_id"]))
    elif change["change_type"] == "member_role":
        if payload.get("action") == "remove":
            cursor.execute("DELETE FROM club_memberships WHERE user_id=%s AND club_id=%s", (change["target_id"], club_id))
        else:
            cursor.execute("UPDATE club_memberships SET role=%s WHERE user_id=%s AND club_id=%s", (payload["new_role"], change["target_id"], club_id))
    elif change["change_type"] == "event_delete":
        cursor.execute("DELETE FROM events WHERE id=%s AND club_id=%s", (change["target_id"], club_id))
    elif change["change_type"] == "club_details":
        d = payload
        if d.get("image"):
            cursor.execute("UPDATE clubs SET name=%s, category=%s, description=%s, about=%s, vision=%s, mission=%s, image=%s WHERE id=%s",
                           (d.get("name"), d.get("category"), d.get("description"), d.get("about"), d.get("vision"), d.get("mission"), d.get("image"), club_id))
        else:
            cursor.execute("UPDATE clubs SET name=%s, category=%s, description=%s, about=%s, vision=%s, mission=%s WHERE id=%s",
                           (d.get("name"), d.get("category"), d.get("description"), d.get("about"), d.get("vision"), d.get("mission"), club_id))
    cursor.execute("UPDATE pending_changes SET status='approved', reviewed_by=%s, reviewed_at=NOW() WHERE id=%s", (user_id, change_id))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Change approved and applied"})


@csrf_exempt
@login_required
def reject_pending_change(request, club_id, change_id):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    user_id = request.session["user_id"]
    data    = _json(request)
    note    = data.get("note", "")
    cursor, conn = get_cursor()
    role = _get_role(user_id, club_id, cursor)
    if role != "president":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Only president can reject changes"}, status=403)
    cursor.execute("UPDATE pending_changes SET status='rejected', reviewed_by=%s, review_note=%s, reviewed_at=NOW() WHERE id=%s AND club_id=%s",
                   (user_id, note, change_id, club_id))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Change rejected"})


@login_required
def my_submitted_changes(request, club_id):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT pc.id, pc.change_type, pc.target_id, pc.payload, pc.status,
               pc.review_note, pc.created_at, pc.reviewed_at, reviewer.name AS reviewed_by_name
        FROM pending_changes pc LEFT JOIN users reviewer ON pc.reviewed_by=reviewer.id
        WHERE pc.club_id=%s AND pc.changed_by=%s ORDER BY pc.created_at DESC LIMIT 50
    """, (club_id, user_id))
    changes = cursor.fetchall()
    enriched = []
    for ch in changes:
        if ch.get("created_at"):  ch["created_at"]  = ch["created_at"].strftime("%Y-%m-%d %H:%M")
        if ch.get("reviewed_at"): ch["reviewed_at"] = ch["reviewed_at"].strftime("%Y-%m-%d %H:%M")
        try: ch["payload_parsed"] = json.loads(ch.get("payload") or "{}")
        except: ch["payload_parsed"] = {}
        if ch["change_type"] == "event_edit":
            cursor.execute("SELECT title FROM events WHERE id=%s", (ch["target_id"],))
            ev = cursor.fetchone()
            ch["target_name"] = ev["title"] if ev else f"Event #{ch['target_id']}"
        elif ch["change_type"] == "member_role":
            cursor.execute("SELECT name FROM users WHERE id=%s", (ch["target_id"],))
            mem = cursor.fetchone()
            ch["target_name"] = mem["name"] if mem else f"User #{ch['target_id']}"
        else:
            ch["target_name"] = ""
        enriched.append(ch)
    close_connection(cursor, conn)
    return JsonResponse(enriched, safe=False)

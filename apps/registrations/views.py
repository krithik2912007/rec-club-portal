import json
from datetime import datetime, date, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from apps.db import get_cursor, close_connection, serialize_row, serialize_rows, log_activity
from apps.decorators import login_required
from apps.email_service import send_email


def _promote_from_waitlist(cursor, conn, event_id):
    """When a seat opens up, auto-register the next person on the waitlist."""
    cursor.execute("""
        SELECT ew.user_id, u.name, u.email
        FROM event_waitlist ew
        JOIN users u ON ew.user_id = u.id
        WHERE ew.event_id = %s
        ORDER BY ew.created_at ASC
        LIMIT 1
    """, (event_id,))
    next_user = cursor.fetchone()
    if not next_user:
        return  # Nobody on waitlist
    try:
        cursor.execute(
            "INSERT INTO registrations(user_id, event_id, status) VALUES(%s, %s, 'registered')",
            (next_user["user_id"], event_id)
        )
        cursor.execute(
            "DELETE FROM event_waitlist WHERE event_id=%s AND user_id=%s",
            (event_id, next_user["user_id"])
        )
        # Notify the promoted user
        cursor.execute("SELECT title FROM events WHERE id=%s", (event_id,))
        ev = cursor.fetchone()
        if ev:
            log_activity(cursor, f"Waitlist: {next_user['name']} auto-registered for '{ev['title']}'")
            from apps.email_service import send_email
            try:
                send_email(
                    next_user["email"],
                    f"🎉 You're registered! — {ev['title']}",
                    f"Hello {next_user['name']},\n\nGreat news! A spot opened up and you have been automatically registered for {ev['title']} from the waitlist.\n\n— Centralized Club Portal"
                )
            except Exception:
                pass
    except Exception:
        pass  # Already registered or other error



def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


# ══════════════════════════════════════
# REGISTER FOR EVENT
# ══════════════════════════════════════
@csrf_exempt
@login_required
def register(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data     = _json(request)
    event_id = data.get("event_id")
    user_id  = request.session["user_id"]
    if not event_id:
        return JsonResponse({"message": "Event id required"}, status=400)
    cursor, conn = get_cursor()
    cursor.execute("SELECT capacity, status, created_by, date FROM events WHERE id=%s", (event_id,))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)
    if event["date"] and event["date"] < date.today():
        close_connection(cursor, conn)
        return JsonResponse({"message": "Registration closed"}, status=400)
    if event["status"] != "approved":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not open for registration"}, status=400)
    if event["created_by"] == user_id:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event creator cannot register"}, status=400)
    cursor.execute("SELECT status FROM registrations WHERE user_id=%s AND event_id=%s", (user_id, event_id))
    existing = cursor.fetchone()
    if existing and existing["status"] == "registered":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Already registered"}, status=400)
    cursor.execute("SELECT COUNT(*) AS total FROM registrations WHERE event_id=%s AND status='registered'", (event_id,))
    count    = cursor.fetchone()["total"]
    capacity = event.get("capacity") or 0
    if capacity and count >= capacity:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event is full"}, status=400)
    if existing:
        cursor.execute("UPDATE registrations SET status='registered' WHERE user_id=%s AND event_id=%s", (user_id, event_id))
    else:
        cursor.execute("INSERT INTO registrations(user_id, event_id, status) VALUES(%s,%s,'registered')", (user_id, event_id))
    cursor.execute("SELECT name, email FROM users WHERE id=%s", (user_id,))
    user_info = cursor.fetchone()
    cursor.execute("SELECT title FROM events WHERE id=%s", (event_id,))
    event_info = cursor.fetchone()
    log_activity(cursor, f"User {user_info['name']} ({user_info['email']}) registered for '{event_info['title']}'")
    conn.commit()
    close_connection(cursor, conn)
    try:
        send_email(user_info["email"], "Event Registration Confirmation",
                   f"Hello {user_info['name']},\n\nThanks for registering for: {event_info['title']}\n\n— REC Club Portal")
    except Exception:
        pass
    return JsonResponse({"message": "Registered successfully"})


# ══════════════════════════════════════
# CANCEL REGISTRATION
# ══════════════════════════════════════
@csrf_exempt
@login_required
def cancel_registration(request):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data     = _json(request)
    event_id = data.get("event_id")
    user_id  = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("SELECT id, title, date, time, location, is_paid, event_category FROM events WHERE id=%s", (event_id,))
    event_info = cursor.fetchone()
    if not event_info:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)
    if event_info["is_paid"]:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Cancellation not allowed for paid events.", "blocked": True}, status=400)
    cursor.execute("SELECT id, team_id FROM registrations WHERE user_id=%s AND event_id=%s AND status='registered'", (user_id, event_id))
    existing = cursor.fetchone()
    if not existing:
        close_connection(cursor, conn)
        return JsonResponse({"message": "You are not registered for this event"}, status=400)
    team_id = existing["team_id"]
    is_team = event_info["event_category"] == "team" and team_id is not None
    def fmt_time(t):
        if isinstance(t, timedelta):
            total = int(t.total_seconds())
            return "{:02d}:{:02d}".format(total // 3600, (total % 3600) // 60)
        return str(t)[:5]
    time_str = fmt_time(event_info["time"])
    cursor.execute("SELECT name, email FROM users WHERE id=%s", (user_id,))
    current_user = cursor.fetchone()
    if is_team:
        cursor.execute("""
            SELECT r.user_id, u.name, u.email FROM registrations r JOIN users u ON r.user_id=u.id
            WHERE r.team_id=%s AND r.event_id=%s AND r.status='registered'
        """, (team_id, event_id))
        team_members = cursor.fetchall()
        cursor.execute("SELECT team_name FROM teams WHERE id=%s", (team_id,))
        team_row  = cursor.fetchone()
        team_name = team_row["team_name"] if team_row else "Your team"
        # FIX: DELETE registrations and the team record entirely instead of just marking cancelled
        # This frees up capacity slots and keeps DB clean
        cursor.execute("DELETE FROM registrations WHERE team_id=%s AND event_id=%s", (team_id, event_id))
        cursor.execute("DELETE FROM teams WHERE id=%s", (team_id,))
        log_activity(cursor, f"Team '{team_name}' cancelled registration for '{event_info['title']}' ({len(team_members)} members removed)")
        _promote_from_waitlist(cursor, conn, event_id)
        conn.commit()
        close_connection(cursor, conn)
        for member in team_members:
            try:
                send_email(member["email"], f"Team Registration Cancelled — {event_info['title']}",
                           f"Hello {member['name']},\n\nTeam '{team_name}' registration for {event_info['title']} was cancelled.\n\n— REC Club Portal")
            except Exception:
                pass
        return JsonResponse({"message": f"Team '{team_name}' registration cancelled and removed."})
    else:
        cursor.execute("DELETE FROM registrations WHERE user_id=%s AND event_id=%s", (user_id, event_id))
        log_activity(cursor, f"User {current_user['name']} cancelled registration for '{event_info['title']}'")
        _promote_from_waitlist(cursor, conn, event_id)
        conn.commit()
        close_connection(cursor, conn)
        if current_user:
            try:
                send_email(current_user["email"], f"Registration Cancelled — {event_info['title']}",
                           f"Hello {current_user['name']},\n\nYour registration for {event_info['title']} was cancelled.\n\n— REC Club Portal")
            except Exception:
                pass
        return JsonResponse({"message": "Registration cancelled successfully"})


# ══════════════════════════════════════
# MY REGISTRATIONS
# ══════════════════════════════════════
@login_required
def my_registrations(request):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.*, c.name AS club_name, r.status FROM registrations r
        JOIN events e ON r.event_id=e.id JOIN clubs c ON e.club_id=c.id
        WHERE r.user_id=%s ORDER BY e.date ASC
    """, (request.session["user_id"],))
    events = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(events, safe=False)


# ══════════════════════════════════════
# EVENT REGISTRATIONS LIST
# ══════════════════════════════════════
@login_required
def event_registrations(request, event_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT u.name, u.email, u.department, u.year FROM registrations r
        JOIN users u ON r.user_id=u.id
        WHERE r.event_id=%s AND r.status='registered' ORDER BY u.name
    """, (event_id,))
    students = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse(students, safe=False)


# ══════════════════════════════════════
# REGISTRATION STATUS
# ══════════════════════════════════════
@login_required
def registration_status(request, event_id):
    cursor, conn = get_cursor()
    cursor.execute("SELECT status FROM registrations WHERE user_id=%s AND event_id=%s",
                   (request.session["user_id"], event_id))
    reg = cursor.fetchone()
    close_connection(cursor, conn)
    if not reg:
        return JsonResponse({"registered": False})
    return JsonResponse({"registered": reg["status"] == "registered", "status": reg["status"]})


# ══════════════════════════════════════
# CART
# ══════════════════════════════════════
@login_required
def get_cart(request):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT c.id AS cart_id, e.id AS event_id, e.title, e.date, e.time, e.location,
               e.price, e.event_category, e.is_paid, cl.name AS club_name, c.team_id, t.team_name
        FROM cart c JOIN events e ON c.event_id=e.id JOIN clubs cl ON e.club_id=cl.id
        LEFT JOIN teams t ON c.team_id=t.id WHERE c.user_id=%s ORDER BY c.added_at DESC
    """, (user_id,))
    items = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(items, safe=False)


@csrf_exempt
@login_required
def add_to_cart(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data     = _json(request)
    event_id = data.get("event_id")
    team_id  = data.get("team_id")
    user_id  = request.session["user_id"]
    if not event_id:
        return JsonResponse({"message": "Event ID required"}, status=400)
    cursor, conn = get_cursor()
    cursor.execute("SELECT id, title, is_paid, status, event_category, capacity FROM events WHERE id=%s", (event_id,))
    event = cursor.fetchone()
    if not event:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)
    if event["status"] != "approved":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not open for registration"}, status=400)
    if not event["is_paid"]:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Free events do not require cart."}, status=400)
    cursor.execute("SELECT id FROM registrations WHERE user_id=%s AND event_id=%s", (user_id, event_id))
    if cursor.fetchone():
        close_connection(cursor, conn)
        return JsonResponse({"message": "Already registered for this event"}, status=400)
    cursor.execute("""
        SELECT p.id, e.title AS event_title FROM payments p JOIN events e ON p.event_id=e.id
        WHERE p.user_id=%s AND p.status='pending' AND p.expires_at > NOW()
    """, (user_id,))
    pending = cursor.fetchall()
    try:
        cursor.execute("INSERT INTO cart(user_id, event_id, team_id) VALUES(%s,%s,%s)", (user_id, event_id, team_id))
        conn.commit()
    except Exception:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event already in cart"}, status=400)
    close_connection(cursor, conn)
    response = {"message": "Added to cart"}
    if pending:
        titles = ", ".join(p["event_title"] for p in pending)
        response["warning"] = f"Payment pending for: {titles}. Please complete payment."
    return JsonResponse(response)


@csrf_exempt
@login_required
def remove_from_cart(request, event_id):
    if request.method != "DELETE":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("DELETE FROM cart WHERE user_id=%s AND event_id=%s", (user_id, event_id))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Removed from cart"})


@csrf_exempt
@login_required
def checkout(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data       = _json(request)
    event_id   = data.get("event_id")
    payment_id = data.get("payment_id")
    method     = data.get("method", "mock")
    txn_ref    = data.get("txn_ref", f"MOCK_{payment_id}")
    user_id    = request.session["user_id"]
    if not event_id:
        return JsonResponse({"message": "Event ID required"}, status=400)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT * FROM payments WHERE id=%s AND user_id=%s AND status='pending'
    """, (payment_id, user_id))
    payment = cursor.fetchone()
    if not payment:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Payment not found or already processed"}, status=404)
    if payment["expires_at"] and datetime.now() > payment["expires_at"]:
        cursor.execute("UPDATE payments SET status='expired' WHERE id=%s", (payment_id,))
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Payment window expired. Please try again."}, status=400)
    team_id = payment["team_id"]
    cursor.execute("UPDATE payments SET status='success', payment_method=%s, txn_ref=%s, completed_at=NOW() WHERE id=%s",
                   (method, txn_ref, payment_id))
    if team_id:
        cursor.execute("UPDATE registrations SET status='registered' WHERE team_id=%s AND event_id=%s AND status='pending_payment'",
                       (team_id, event_id))
    else:
        cursor.execute("INSERT INTO registrations(user_id, event_id, status) VALUES(%s,%s,'registered') ON DUPLICATE KEY UPDATE status='registered'",
                       (user_id, event_id))
    cursor.execute("DELETE FROM cart WHERE user_id=%s AND event_id=%s", (user_id, event_id))
    cursor.execute("SELECT name, email FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    cursor.execute("SELECT title FROM events WHERE id=%s", (event_id,))
    event = cursor.fetchone()
    if user and event:
        log_activity(cursor, f"Payment successful: {user['name']} paid for '{event['title']}' (Txn: {txn_ref})")
    conn.commit()
    close_connection(cursor, conn)
    if user and event:
        try:
            send_email(user["email"], "Payment Confirmation — Event Registration",
                       f"Hi {user['name']},\n\nPayment successful for {event['title']}!\nTxn Ref: {txn_ref}\n\n— REC Club Portal")
        except Exception:
            pass
    return JsonResponse({"message": "Payment successful! You are now registered.", "txn_ref": txn_ref})


# ══════════════════════════════════════
# TEAMS
# ══════════════════════════════════════
def _validate_members(reg_nos, cursor):
    users = []
    for reg in reg_nos:
        reg = reg.strip()
        if not reg:
            continue
        cursor.execute("SELECT id, name, email, reg_no FROM users WHERE reg_no=%s", (reg,))
        user = cursor.fetchone()
        if not user:
            return None, f"Register number '{reg}' not found in the system"
        users.append(user)
    return users, None


@csrf_exempt
@login_required
def create_team(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data      = _json(request)
    event_id  = data.get("event_id")
    team_name = (data.get("team_name") or "").strip()
    reg_nos   = data.get("members", [])
    user_id   = request.session["user_id"]
    if not event_id or not team_name:
        return JsonResponse({"message": "Event ID and team name are required"}, status=400)
    cursor, conn = get_cursor()
    cursor.execute("SELECT id, title, event_category, min_members, max_members, is_paid, status, capacity FROM events WHERE id=%s", (event_id,))
    event = cursor.fetchone()
    if not event or event["status"] != "approved":
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not available"}, status=404)
    if event["event_category"] != "team":
        close_connection(cursor, conn)
        return JsonResponse({"message": "This is not a team event"}, status=400)
    min_m = event["min_members"] or 2
    max_m = event["max_members"] or 99
    if len(reg_nos) < min_m or len(reg_nos) > max_m:
        close_connection(cursor, conn)
        return JsonResponse({"message": f"Team size must be between {min_m} and {max_m} members"}, status=400)
    members, err = _validate_members(reg_nos, cursor)
    if err:
        close_connection(cursor, conn)
        return JsonResponse({"message": err}, status=400)
    cursor.execute("SELECT id FROM teams WHERE event_id=%s AND team_name=%s", (event_id, team_name))
    if cursor.fetchone():
        close_connection(cursor, conn)
        return JsonResponse({"message": "Team name already taken for this event"}, status=400)
    for m in members:
        cursor.execute("SELECT id FROM registrations WHERE user_id=%s AND event_id=%s AND status='registered'", (m["id"], event_id))
        if cursor.fetchone():
            close_connection(cursor, conn)
            return JsonResponse({"message": f"{m['name']} (Reg: {m['reg_no']}) is already registered"}, status=400)
    cursor.execute("SELECT COUNT(*) AS total FROM registrations WHERE event_id=%s AND status='registered'", (event_id,))
    registered_count = cursor.fetchone()["total"]
    capacity = event.get("capacity") or 0
    if capacity and (registered_count + len(members)) > capacity:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Not enough seats for this team"}, status=400)
    status_val = "pending_payment" if event["is_paid"] else "registered"
    cursor.execute("INSERT INTO teams(event_id, team_name, leader_id) VALUES(%s,%s,%s)", (event_id, team_name, user_id))
    team_id = cursor.lastrowid
    for m in members:
        try:
            cursor.execute("""
                INSERT INTO registrations(user_id, event_id, team_id, status) VALUES(%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE status=%s, team_id=%s
            """, (m["id"], event_id, team_id, status_val, status_val, team_id))
        except Exception:
            pass
    conn.commit()
    log_activity(cursor, f"Team '{team_name}' registered for '{event['title']}' by user {user_id} ({len(members)} members)")
    if not event["is_paid"]:
        for m in members:
            try:
                send_email(m["email"], f"Team Registration Confirmation — {event['title']}",
                           f"Hi {m['name']},\n\nYou are registered in team '{team_name}' for {event['title']}!\n\n— REC Club Portal")
            except Exception:
                pass
    close_connection(cursor, conn)
    return JsonResponse({"message": "Team registered successfully!" if not event["is_paid"] else "Team created. Proceed to cart for payment.",
                         "team_id": team_id, "team_name": team_name, "members": [m["name"] for m in members]})


@csrf_exempt
@login_required
def join_team(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data      = _json(request)
    team_id   = data.get("team_id")
    user_id   = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("SELECT * FROM teams WHERE id=%s", (team_id,))
    team = cursor.fetchone()
    if not team:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Team not found"}, status=404)
    try:
        cursor.execute("INSERT INTO registrations(user_id, event_id, team_id, status) VALUES(%s,%s,%s,'registered')",
                       (user_id, team["event_id"], team_id))
        conn.commit()
    except Exception:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Already in this team"}, status=400)
    close_connection(cursor, conn)
    return JsonResponse({"message": "Joined team successfully"})


@login_required
def get_event_teams(request, event_id):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT t.id, t.team_name, u.name AS leader_name, COUNT(r.id) AS member_count
        FROM teams t JOIN users u ON t.leader_id=u.id
        LEFT JOIN registrations r ON r.team_id=t.id AND r.status='registered'
        WHERE t.event_id=%s GROUP BY t.id ORDER BY t.team_name
    """, (event_id,))
    teams = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse(teams, safe=False)


@login_required
def my_teams(request):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT t.id, t.team_name, e.title AS event_title, e.date, r.status
        FROM registrations r JOIN teams t ON r.team_id=t.id JOIN events e ON r.event_id=e.id
        WHERE r.user_id=%s AND r.team_id IS NOT NULL ORDER BY e.date DESC
    """, (user_id,))
    teams = serialize_rows(cursor.fetchall())
    close_connection(cursor, conn)
    return JsonResponse(teams, safe=False)


# ── CANCEL REGISTRATION BY ID (URL param version) ──
@csrf_exempt
@login_required
def cancel_registration_by_id(request, event_id):
    """Same as cancel_registration but event_id comes from URL, not body."""
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    # Inject event_id into request body handler
    request._event_id_override = event_id
    # Reuse existing logic
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("SELECT id, title, date, time, location, is_paid, event_category FROM events WHERE id=%s", (event_id,))
    event_info = cursor.fetchone()
    if not event_info:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Event not found"}, status=404)
    if event_info["is_paid"]:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Cancellation not allowed for paid events.", "blocked": True}, status=400)
    cursor.execute("SELECT id, team_id FROM registrations WHERE user_id=%s AND event_id=%s AND status='registered'", (user_id, event_id))
    existing = cursor.fetchone()
    if not existing:
        close_connection(cursor, conn)
        return JsonResponse({"message": "You are not registered for this event"}, status=400)
    team_id = existing["team_id"]
    is_team = event_info["event_category"] == "team" and team_id is not None
    if is_team:
        # DELETE all team registrations and the team record
        cursor.execute("SELECT team_name FROM teams WHERE id=%s", (team_id,))
        team_row  = cursor.fetchone()
        team_name = team_row["team_name"] if team_row else "Your team"
        cursor.execute("DELETE FROM registrations WHERE team_id=%s AND event_id=%s", (team_id, event_id))
        cursor.execute("DELETE FROM teams WHERE id=%s", (team_id,))
        log_activity(cursor, f"Team '{team_name}' cancelled registration for event {event_id}")
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": f"Team '{team_name}' registration cancelled and removed."})
    else:
        cursor.execute("DELETE FROM registrations WHERE user_id=%s AND event_id=%s", (user_id, event_id))
        log_activity(cursor, f"User {user_id} cancelled registration for event {event_id}")
        _promote_from_waitlist(cursor, conn, event_id)
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Registration cancelled successfully"})


# ── CONFIRM PAYMENT ──
@csrf_exempt
@login_required
def confirm_payment(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data     = _json(request)
    event_id = data.get("event_id")
    user_id  = request.session["user_id"]
    if not event_id:
        return JsonResponse({"message": "Event ID required"}, status=400)
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT c.team_id, e.price, e.title FROM cart c JOIN events e ON c.event_id=e.id
        WHERE c.user_id=%s AND c.event_id=%s
    """, (user_id, event_id))
    item = cursor.fetchone()
    if not item:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Item not in cart"}, status=404)
    cursor.execute("SELECT id FROM payments WHERE user_id=%s AND event_id=%s AND status='pending' AND expires_at > NOW()", (user_id, event_id))
    if cursor.fetchone():
        close_connection(cursor, conn)
        return JsonResponse({"message": "Payment already initiated. Complete within 10 minutes."}, status=400)
    cursor.execute("INSERT INTO payments(user_id, event_id, team_id, amount, status) VALUES(%s,%s,%s,%s,'pending')",
                   (user_id, event_id, item["team_id"], item["price"]))
    conn.commit()
    payment_id = cursor.lastrowid
    cursor.execute("SELECT expires_at FROM payments WHERE id=%s", (payment_id,))
    pay_row    = cursor.fetchone()
    close_connection(cursor, conn)
    expires_at = pay_row["expires_at"].strftime("%Y-%m-%d %H:%M:%S") if pay_row and pay_row.get("expires_at") else None
    return JsonResponse({
        "message":    "Payment initiated. Complete within 10 minutes.",
        "payment_id": payment_id,
        "amount":     float(item["price"]),
        "event_title": item["title"],
        "expires_at": expires_at,
        "mock_options": ["gpay", "phonepe", "upi_qr", "netbanking"]
    })


# ── PAYMENT SUCCESS ──
@csrf_exempt
@login_required
def payment_success(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data       = _json(request)
    payment_id = data.get("payment_id")
    method     = data.get("method", "mock")
    txn_ref    = data.get("txn_ref", f"MOCK_{payment_id}")
    user_id    = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("SELECT * FROM payments WHERE id=%s AND user_id=%s AND status='pending'", (payment_id, user_id))
    payment = cursor.fetchone()
    if not payment:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Payment not found or already processed"}, status=404)
    if payment["expires_at"] and datetime.now() > payment["expires_at"]:
        cursor.execute("UPDATE payments SET status='expired' WHERE id=%s", (payment_id,))
        conn.commit()
        close_connection(cursor, conn)
        return JsonResponse({"message": "Payment window expired. Please try again."}, status=400)
    event_id = payment["event_id"]
    team_id  = payment["team_id"]
    cursor.execute("UPDATE payments SET status='success', payment_method=%s, txn_ref=%s, completed_at=NOW() WHERE id=%s",
                   (method, txn_ref, payment_id))
    if team_id:
        cursor.execute("UPDATE registrations SET status='registered' WHERE team_id=%s AND event_id=%s AND status='pending_payment'",
                       (team_id, event_id))
    else:
        cursor.execute("INSERT INTO registrations(user_id, event_id, status) VALUES(%s,%s,'registered') ON DUPLICATE KEY UPDATE status='registered'",
                       (user_id, event_id))
    cursor.execute("DELETE FROM cart WHERE user_id=%s AND event_id=%s", (user_id, event_id))
    cursor.execute("SELECT name, email FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    cursor.execute("SELECT title FROM events WHERE id=%s", (event_id,))
    event = cursor.fetchone()
    if user and event:
        log_activity(cursor, f"Payment successful: {user['name']} paid for '{event['title']}' (Txn: {txn_ref})")
    conn.commit()
    close_connection(cursor, conn)
    if user and event:
        try:
            send_email(user["email"], "Payment Confirmation — Event Registration",
                       f"Hi {user['name']},\n\nPayment successful for {event['title']}!\nTxn Ref: {txn_ref}\n\n— REC Club Portal")
        except Exception:
            pass
    return JsonResponse({"message": "Payment successful! You are now registered.", "txn_ref": txn_ref})


# ── PAYMENT STATUS ──
@login_required
def payment_status(request, payment_id):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("SELECT id, status, expires_at, amount, payment_method, txn_ref FROM payments WHERE id=%s AND user_id=%s",
                   (payment_id, user_id))
    payment = cursor.fetchone()
    close_connection(cursor, conn)
    if not payment:
        return JsonResponse({"message": "Payment not found"}, status=404)
    result = serialize_row(payment)
    if result.get("expires_at"):
        try:
            from datetime import datetime as dt
            exp = dt.strptime(result["expires_at"], "%Y-%m-%d %H:%M")
            remaining = (exp - dt.now()).total_seconds()
            result["seconds_remaining"] = max(0, int(remaining))
        except Exception:
            result["seconds_remaining"] = 0
    return JsonResponse(result)


# ── CHECK PENDING PAYMENTS ──
@login_required
def check_pending_payments(request):
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT e.title FROM payments p JOIN events e ON p.event_id=e.id
        WHERE p.user_id=%s AND p.status='pending' AND p.expires_at > NOW()
    """, (user_id,))
    rows = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse({"pending_titles": [r["title"] for r in rows]})


# ── VALIDATE REG NO (team form live check) ──
@csrf_exempt
@login_required
def validate_reg_no(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)
    data   = _json(request)
    reg_no = (data.get("reg_no") or "").strip()
    if not reg_no:
        return JsonResponse({"valid": False, "message": "Enter a register number"}, status=400)
    cursor, conn = get_cursor()
    cursor.execute("SELECT id, name FROM users WHERE reg_no=%s", (reg_no,))
    user = cursor.fetchone()
    close_connection(cursor, conn)
    if user:
        return JsonResponse({"valid": True, "name": user["name"]})
    return JsonResponse({"valid": False, "message": "Register number not found"})
import json
import uuid
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from werkzeug.security import generate_password_hash, check_password_hash
from apps.db import get_cursor, close_connection, serialize_row, log_activity
from apps.decorators import login_required
from apps.email_service import send_email
from apps.token_services import generate_reset_token, verify_reset_token


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


@csrf_exempt
@require_http_methods(["POST"])
def signup(request):
    """
    Step 1: Validate form data, send OTP to email.
    Does NOT create the user yet — waits for OTP verification.
    """
    import random
    from datetime import datetime, timedelta

    data       = _json(request)
    name       = data.get("name", "").strip()
    email      = data.get("email", "").strip().lower()
    password   = data.get("password", "")
    reg_no     = data.get("reg_no", "").strip().upper()
    department = data.get("department", "").strip()
    year       = data.get("year", None)

    if not all([name, email, password, reg_no]):
        return JsonResponse({"message": "Name, email, password and register number are required"}, status=400)

    cursor, conn = get_cursor()

    # Check duplicates before sending OTP
    cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
    if cursor.fetchone():
        close_connection(cursor, conn)
        return JsonResponse({"message": "Email already registered"}, status=400)

    cursor.execute("SELECT id FROM users WHERE reg_no=%s", (reg_no,))
    if cursor.fetchone():
        close_connection(cursor, conn)
        return JsonResponse({"message": "Register number already in use"}, status=400)

    # Generate 6-digit OTP
    otp        = str(random.randint(100000, 999999))
    expires_at = datetime.now() + timedelta(minutes=10)
    hashed_pw  = generate_password_hash(password)

    # Delete any previous OTP for this email
    cursor.execute("DELETE FROM email_otps WHERE email=%s", (email,))

    # Store OTP with all signup data (user created only after verification)
    cursor.execute("""
        INSERT INTO email_otps (email, otp, name, reg_no, password, department, year, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (email, otp, name, reg_no, hashed_pw, department, year or None, expires_at))
    conn.commit()
    close_connection(cursor, conn)

    # Send OTP email
    try:
        send_email(
            email,
            "Your OTP — Centralized Club Portal",
            f"""Hello {name},

Your One-Time Password (OTP) for account verification is:

  {otp}

This OTP is valid for 10 minutes. Do not share it with anyone.

If you did not request this, please ignore this email.

— Centralized Club Portal"""
        )
    except Exception as e:
        print(f"OTP email failed: {e}")
        return JsonResponse({"message": "Failed to send OTP email. Please check your email address."}, status=500)

    return JsonResponse({"message": "OTP sent to your email. Please verify to complete signup.", "step": "verify_otp"})


@csrf_exempt
@require_http_methods(["POST"])
def verify_otp(request):
    """
    Step 2: Verify OTP and create the user account.
    """
    from datetime import datetime

    data  = _json(request)
    email = data.get("email", "").strip().lower()
    otp   = data.get("otp", "").strip()

    if not email or not otp:
        return JsonResponse({"message": "Email and OTP are required"}, status=400)

    cursor, conn = get_cursor()

    cursor.execute("""
        SELECT * FROM email_otps
        WHERE email=%s AND used=FALSE AND expires_at > NOW()
        ORDER BY created_at DESC LIMIT 1
    """, (email,))
    record = cursor.fetchone()

    if not record:
        close_connection(cursor, conn)
        return JsonResponse({"message": "OTP expired or not found. Please sign up again."}, status=400)

    if record["otp"] != otp:
        close_connection(cursor, conn)
        return JsonResponse({"message": "Incorrect OTP. Please try again."}, status=400)

    # Check again for duplicates (race condition safety)
    cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
    if cursor.fetchone():
        close_connection(cursor, conn)
        return JsonResponse({"message": "Email already registered"}, status=400)

    cursor.execute("SELECT id FROM users WHERE reg_no=%s", (record["reg_no"],))
    if cursor.fetchone():
        close_connection(cursor, conn)
        return JsonResponse({"message": "Register number already in use"}, status=400)

    # Mark OTP as used
    cursor.execute("UPDATE email_otps SET used=TRUE WHERE id=%s", (record["id"],))

    # Create the user
    cursor.execute("""
        INSERT INTO users (reg_no, name, email, password, role, department, year)
        VALUES (%s, %s, %s, %s, 'student', %s, %s)
    """, (record["reg_no"], record["name"], email, record["password"],
          record["department"], record["year"]))

    log_activity(cursor, f"New user verified & signed up: {record['name']} ({email}) | Reg No: {record['reg_no']}")
    conn.commit()
    close_connection(cursor, conn)

    return JsonResponse({"message": "Account created successfully! You can now log in.", "success": True})


@csrf_exempt
@require_http_methods(["POST"])
def resend_otp(request):
    """Resend OTP for the same email."""
    import random
    from datetime import datetime, timedelta

    data  = _json(request)
    email = data.get("email", "").strip().lower()

    if not email:
        return JsonResponse({"message": "Email required"}, status=400)

    cursor, conn = get_cursor()

    # Get previous OTP record to reuse signup data
    cursor.execute("""
        SELECT * FROM email_otps WHERE email=%s AND used=FALSE
        ORDER BY created_at DESC LIMIT 1
    """, (email,))
    record = cursor.fetchone()

    if not record:
        close_connection(cursor, conn)
        return JsonResponse({"message": "No pending signup found. Please sign up again."}, status=400)

    # Generate new OTP
    otp        = str(random.randint(100000, 999999))
    expires_at = datetime.now() + timedelta(minutes=10)

    cursor.execute("""
        UPDATE email_otps SET otp=%s, expires_at=%s, created_at=NOW()
        WHERE id=%s
    """, (otp, expires_at, record["id"]))
    conn.commit()
    close_connection(cursor, conn)

    try:
        send_email(
            email,
            "New OTP — Centralized Club Portal",
            f"""Hello {record["name"]},

Your new One-Time Password (OTP) is:

  {otp}

Valid for 10 minutes.

— Centralized Club Portal"""
        )
    except Exception:
        return JsonResponse({"message": "Failed to resend OTP."}, status=500)

    return JsonResponse({"message": "New OTP sent to your email."})


@csrf_exempt
@require_http_methods(["POST"])
def login_view(request):
    data     = _json(request)
    email    = data.get("email")
    password = data.get("password")
    # Note: 'role' field from frontend is intentionally ignored —
    # the actual role is always read from the database.

    if not email or not password:
        return JsonResponse({"message": "Missing credentials"}, status=400)

    cursor, conn = get_cursor()
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()

    if not user or not check_password_hash(user["password"], password):
        close_connection(cursor, conn)
        return JsonResponse({"message": "Invalid credentials"}, status=401)

    request.session.flush()
    request.session["user_id"] = user["id"]
    request.session["role"]    = user["role"]

    cursor.execute("""
        SELECT c.id AS club_id, c.name AS club_name, cm.role AS club_role
        FROM club_memberships cm
        JOIN clubs c ON cm.club_id = c.id
        WHERE cm.user_id = %s
    """, (user["id"],))
    clubs = cursor.fetchall()

    if clubs:
        request.session["active_club"] = clubs[0]["club_id"]
        request.session["club_role"]   = clubs[0]["club_role"]
    else:
        request.session["active_club"] = None
        request.session["club_role"]   = None

    # Force session save so cookie is set before redirect
    request.session.modified = True

    log_activity(cursor, f"User logged in: {user['name']} ({user['email']}) | Role: {user['role']}")
    close_connection(cursor, conn)
    return JsonResponse({
        "message": "Login success",
        "user": {
            "id":     user["id"],
            "name":   user["name"],
            "email":  user["email"],
            "role":   user["role"],
            "reg_no": user["reg_no"],
        },
        "clubs":       clubs,
        "active_club": request.session.get("active_club"),
    })


@csrf_exempt
@require_http_methods(["POST"])
def logout_view(request):
    request.session.flush()
    return JsonResponse({"message": "Logged out"})


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def switch_club(request):
    data    = _json(request)
    club_id = data.get("club_id")
    cursor, conn = get_cursor()
    cursor.execute(
        "SELECT role FROM club_memberships WHERE user_id=%s AND club_id=%s",
        (request.session["user_id"], club_id)
    )
    membership = cursor.fetchone()
    close_connection(cursor, conn)
    if not membership:
        return JsonResponse({"message": "Access denied"}, status=403)
    request.session["active_club"] = club_id
    request.session["club_role"]   = membership["role"]
    request.session.modified = True
    return JsonResponse({"message": "Active club switched"})


@require_http_methods(["GET"])
@login_required
def my_clubs(request):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT c.id, c.name, cm.role
        FROM club_memberships cm
        JOIN clubs c ON cm.club_id = c.id
        WHERE cm.user_id = %s
    """, (request.session["user_id"],))
    clubs = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse(clubs, safe=False)


@require_http_methods(["GET"])
@login_required
def get_current_user(request):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT id, name, email, role, reg_no, department, year, profile_pic
        FROM users WHERE id=%s
    """, (request.session["user_id"],))
    user = cursor.fetchone()
    cursor.execute("""
        SELECT c.id AS club_id, c.name AS club_name, cm.role AS club_role
        FROM club_memberships cm
        JOIN clubs c ON cm.club_id = c.id
        WHERE cm.user_id = %s
    """, (request.session["user_id"],))
    clubs = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse({
        "user":        serialize_row(user),
        "clubs":       clubs,
        "active_club": request.session.get("active_club"),
        "club_role":   request.session.get("club_role"),
    })


@csrf_exempt
@login_required
def update_profile(request):
    if request.method != "PUT":
        return JsonResponse({"message": "Method not allowed"}, status=405)

    # Django does not parse multipart/form-data for PUT requests automatically.
    content_type = request.META.get("CONTENT_TYPE", "")
    if "multipart/form-data" in content_type:
        request.method = "POST"
        request._load_post_and_files()
        request.method = "PUT"

    data    = request.POST
    files   = request.FILES
    user_id = request.session["user_id"]
    cursor, conn = get_cursor()

    profile_pic_path = None
    if "profile_pic" in files:
        pic = files["profile_pic"]
        if pic:
            from django.conf import settings as djsettings
            filename = str(uuid.uuid4()) + "_" + pic.name
            path = os.path.join(djsettings.MEDIA_ROOT, "uploads", filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb+") as f:
                for chunk in pic.chunks():
                    f.write(chunk)
            profile_pic_path = "uploads/" + filename

    if profile_pic_path:
        cursor.execute("""
            UPDATE users SET name=%s, department=%s, year=%s, phone=%s, bio=%s,
            github=%s, linkedin=%s, instagram=%s, profile_pic=%s WHERE id=%s
        """, (data.get("name"), data.get("department"), data.get("year") or None,
              data.get("phone"), data.get("bio"), data.get("github"),
              data.get("linkedin"), data.get("instagram"), profile_pic_path, user_id))
    else:
        cursor.execute("""
            UPDATE users SET name=%s, department=%s, year=%s, phone=%s, bio=%s,
            github=%s, linkedin=%s, instagram=%s WHERE id=%s
        """, (data.get("name"), data.get("department"), data.get("year") or None,
              data.get("phone"), data.get("bio"), data.get("github"),
              data.get("linkedin"), data.get("instagram"), user_id))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Profile updated successfully"})


@require_http_methods(["GET"])
@login_required
def get_profile(request):
    cursor, conn = get_cursor()
    cursor.execute("""
        SELECT id, reg_no, name, email, role, department, year,
               phone, bio, github, linkedin, instagram, profile_pic
        FROM users WHERE id=%s
    """, (request.session["user_id"],))
    user = cursor.fetchone()
    close_connection(cursor, conn)
    return JsonResponse(serialize_row(user))


@csrf_exempt
@require_http_methods(["POST"])
def forgot_password(request):
    data  = _json(request)
    email = data.get("email")
    cursor, conn = get_cursor()
    cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()
    close_connection(cursor, conn)
    if not user:
        return JsonResponse({"message": "Email not found"}, status=404)
    token      = generate_reset_token(email)
    reset_link = f"{request.scheme}://{request.get_host()}/reset-password/{token}"
    send_email(email, "Reset Your Password",
               f"Click the link to reset your password:\n{reset_link}")
    return JsonResponse({"message": "Reset email sent"})


@csrf_exempt
def reset_password(request, token):
    email = verify_reset_token(token)
    if not email:
        return JsonResponse({"message": "Invalid or expired token"}, status=400)
    if request.method == "GET":
        return render(request, "reset_password.html", {"token": token})
    new_password = request.POST.get("password") or _json(request).get("password")
    if not new_password:
        return JsonResponse({"message": "Password required"}, status=400)
    hashed = generate_password_hash(new_password)
    cursor, conn = get_cursor()
    cursor.execute("UPDATE users SET password=%s WHERE email=%s", (hashed, email))
    conn.commit()
    close_connection(cursor, conn)
    return JsonResponse({"message": "Password updated successfully"})


@require_http_methods(["GET"])
@login_required
def user_lookup(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse([], safe=False)
    cursor, conn = get_cursor()
    # FIX: Use LIKE for partial matching so autocomplete/live-search works
    cursor.execute("""
        SELECT id, reg_no, name, email, role, department, year
        FROM users WHERE email LIKE %s OR reg_no LIKE %s LIMIT 5
    """, (f"%{query}%", f"%{query.upper()}%"))
    users = cursor.fetchall()
    close_connection(cursor, conn)
    return JsonResponse(users, safe=False)
"""
decorators.py — Role-based access control.
Identical role hierarchy to Flask version.
Adapted to use Django's JsonResponse and request.session.
"""
from functools import wraps
from django.http import JsonResponse
from apps.db import get_cursor, close_connection

# ── Role Sets ──
EVENT_MANAGEMENT_ROLES = {
    "president", "vice_president", "event_coordinator",
    "event_management_head", "event_management_associate"
}
LEADERSHIP_ROLES  = {"president", "vice_president"}
ALL_MEMBER_ROLES  = {
    "president", "vice_president", "secretary", "joint_secretary",
    "treasurer", "hr", "event_coordinator",
    "event_management_head", "event_management_associate",
    "pr_head", "pr_associate", "photography"
}
VIEW_ONLY_ROLES = ALL_MEMBER_ROLES - EVENT_MANAGEMENT_ROLES

ROLE_LABELS = {
    "president":                  "President",
    "vice_president":             "Vice President",
    "secretary":                  "Secretary",
    "joint_secretary":            "Joint Secretary",
    "treasurer":                  "Treasurer",
    "hr":                         "HR",
    "event_coordinator":          "Event Coordinator",
    "event_management_head":      "Event Management Head",
    "event_management_associate": "Event Management Associate",
    "pr_head":                    "PR Head",
    "pr_associate":               "PR Associate",
    "photography":                "Photography",
}

def is_president(role):      return role == "president"
def is_leadership(role):     return role in LEADERSHIP_ROLES
def can_manage_events(role): return role in EVENT_MANAGEMENT_ROLES
def is_member(role):         return role in ALL_MEMBER_ROLES
def role_label(role):        return ROLE_LABELS.get(role, (role or "").replace("_", " ").title())


def login_required(f):
    @wraps(f)
    def wrapper(request, *args, **kwargs):
        if "user_id" not in request.session:
            return JsonResponse({"message": "Login required"}, status=401)
        return f(request, *args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(request, *args, **kwargs):
        if "user_id" not in request.session:
            return JsonResponse({"message": "Login required"}, status=401)
        if request.session.get("role") != "admin":
            return JsonResponse({"message": "Admin access required"}, status=403)
        return f(request, *args, **kwargs)
    return wrapper


def club_member_required(f):
    @wraps(f)
    def wrapper(request, *args, **kwargs):
        club_id = kwargs.get("club_id")
        user_id = request.session.get("user_id")
        if not user_id:
            return JsonResponse({"message": "Login required"}, status=401)
        cursor, conn = get_cursor()
        cursor.execute(
            "SELECT role FROM club_memberships WHERE user_id=%s AND club_id=%s",
            (user_id, club_id)
        )
        membership = cursor.fetchone()
        close_connection(cursor, conn)
        if not membership:
            return JsonResponse({"message": "Not a club member"}, status=403)
        return f(request, *args, **kwargs)
    return wrapper


def president_required(f):
    @wraps(f)
    def wrapper(request, *args, **kwargs):
        club_id = kwargs.get("club_id")
        user_id = request.session.get("user_id")
        if not user_id:
            return JsonResponse({"message": "Login required"}, status=401)
        cursor, conn = get_cursor()
        cursor.execute(
            "SELECT role FROM club_memberships WHERE user_id=%s AND club_id=%s",
            (user_id, club_id)
        )
        member = cursor.fetchone()
        close_connection(cursor, conn)
        if not member:
            return JsonResponse({"message": "Not a club member"}, status=403)
        if not is_leadership(member["role"]):
            return JsonResponse({"message": "President/Vice President access required"}, status=403)
        return f(request, *args, **kwargs)
    return wrapper


def coordinator_required(f):
    @wraps(f)
    def wrapper(request, *args, **kwargs):
        club_id = kwargs.get("club_id")
        user_id = request.session.get("user_id")
        if not user_id:
            return JsonResponse({"message": "Login required"}, status=401)
        cursor, conn = get_cursor()
        cursor.execute(
            "SELECT role FROM club_memberships WHERE user_id=%s AND club_id=%s",
            (user_id, club_id)
        )
        member = cursor.fetchone()
        close_connection(cursor, conn)
        if not member:
            return JsonResponse({"message": "Not a club member"}, status=403)
        if not can_manage_events(member["role"]):
            return JsonResponse({"message": "Event management access required"}, status=403)
        return f(request, *args, **kwargs)
    return wrapper

from django.urls import path
from . import views

urlpatterns = [
    # Club management
    path('admin/clubs',                                 views.admin_clubs,              name='admin_clubs'),
    path('admin/clubs/<int:club_id>',                   views.admin_club_detail,        name='admin_club_detail'),
    path('admin/clubs/<int:club_id>/members',           views.admin_club_members,       name='admin_club_members'),
    path('admin/clubs/<int:club_id>/members/<int:user_id>', views.admin_club_member_detail, name='admin_club_member_detail'),
    # Event management
    path('admin/events',                                views.admin_events,             name='admin_events'),
    path('admin/events/<int:event_id>',                 views.admin_event_detail,       name='admin_event_detail'),
    path('admin/events/<int:event_id>/approve',         views.admin_approve_event,      name='admin_approve_event'),
    path('admin/events/<int:event_id>/reject',          views.admin_reject_event,       name='admin_reject_event'),
    path('admin/events/<int:event_id>/gallery',         views.admin_upload_gallery,     name='admin_upload_gallery'),
    path('admin/events/<int:event_id>/gallery/<int:image_id>', views.admin_delete_gallery_image, name='admin_delete_gallery_image'),
    path('admin/events/<int:event_id>/pending-edit',    views.admin_apply_pending_edit, name='admin_apply_pending_edit'),
    path('admin/pending-events',                        views.admin_pending_events,     name='admin_pending_events'),
    # Users
    path('api/admin/all-users',                         views.admin_all_users,          name='admin_all_users'),
    path('api/admin/users/<int:user_id>',               views.admin_user_detail,        name='admin_user_detail'),
    path('api/admin/users/<int:user_id>/promote',       views.admin_promote_user,       name='admin_promote_user'),
    # Analytics & reports
    path('admin/event-analytics',                       views.admin_event_analytics,    name='admin_event_analytics'),
    path('admin/favorite-analytics',                    views.admin_favorite_analytics, name='admin_favorite_analytics'),
    path('admin/revenue-analytics',                     views.admin_revenue_analytics,  name='admin_revenue_analytics'),
    # Activity & misc
    path('api/admin/activity',                          views.admin_activity,           name='admin_activity'),
    path('api/admin/rejected-events',                   views.admin_rejected_events,    name='admin_rejected_events'),
    path('api/admin/pending-changes',                   views.admin_pending_changes,    name='admin_pending_changes'),
    path('admin/test-email',                            views.admin_test_email,         name='admin_test_email'),
    # Club roles
    path('api/clubs/<int:club_id>/roles',               views.club_roles,               name='club_roles'),
    path('api/clubs/<int:club_id>/roles/<str:role_name>', views.club_role_detail,       name='club_role_detail'),
    # Media serving
    path('uploads/<str:filename>',                      views.serve_upload,             name='serve_upload'),
]

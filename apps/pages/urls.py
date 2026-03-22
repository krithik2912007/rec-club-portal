from django.urls import path
from . import views

urlpatterns = [
    path('',                        views.index,            name='index'),
    path('home',                    views.home,             name='home'),
    path('clubs',                   views.clubs_page,       name='clubs_page'),
    path('events',                  views.events_page,      name='events_page'),
    path('calendar',                views.calendar_page,    name='calendar_page'),
    path('club/<int:club_id>',      views.club_detail_page, name='club_detail_page'),
    path('event/<int:event_id>',    views.event_detail_page,name='event_detail_page'),
    path('dashboard',               views.dashboard,        name='dashboard'),
    path('club-dashboard',          views.club_dashboard,   name='club_dashboard'),
    path('admin',                   views.admin_dashboard,  name='admin_dashboard'),
    path('attendance/<int:event_id>/scan', views.attendance_scan_page, name='attendance_scan'),
    path('api/stats',               views.get_stats,        name='get_stats'),
    path('api/upcoming-events',     views.upcoming_events,  name='upcoming_events_page'),
    path('api/admin/stats',         views.admin_stats,      name='admin_stats'),
]

# ── President / Club management routes ──
from . import president_views as pv

urlpatterns += [
    path('api/club/<int:club_id>/pending-changes',                  pv.get_pending_changes,         name='get_pending_changes'),
    path('api/club/<int:club_id>/pending-changes/<int:change_id>/approve', pv.approve_pending_change, name='approve_pending_change'),
    path('api/club/<int:club_id>/pending-changes/<int:change_id>/reject',  pv.reject_pending_change,  name='reject_pending_change'),
    path('api/events/<int:event_id>/president-approve',             pv.president_approve_event,     name='president_approve_event'),
    path('api/events/<int:event_id>/president-reject',              pv.president_reject_event,      name='president_reject_event'),
    path('api/pending-events/<int:club_id>',                        pv.get_pending_events,          name='get_pending_events'),
    path('api/notifications',                                       pv.get_notifications,           name='get_notifications'),
    path('api/notifications/<int:notif_id>/read',                   pv.mark_notification_read,      name='mark_notification_read'),
    path('api/notifications/read-all',                              pv.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('api/my-coordinator-events',                               pv.my_coordinator_events,       name='my_coordinator_events'),
]
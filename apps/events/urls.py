from django.urls import path
from . import views

urlpatterns = [
    # Listing
    path('events',                                              views.get_events,               name='get_events'),
    path('events/popular',                                      views.popular_events,           name='popular_events'),
    path('events/favourited',                                   views.favourited_events,        name='favourited_events'),
    path('events/check-conflict',                               views.check_event_conflict,     name='check_event_conflict'),
    path('events/create',                                       views.create_event,             name='create_event'),

    # Single event — plural prefix
    path('events/<int:event_id>',                               views.get_event_detail,             name='get_event_detail_p'),
    path('events/<int:event_id>/favorite',                      views.toggle_favourite_event,       name='toggle_favourite_event'),
    path('events/<int:event_id>/favourite',                     views.toggle_favourite_event,       name='toggle_favourite_event2'),
    path('events/<int:event_id>/feedback',                      views.get_event_feedback,           name='get_event_feedback_p'),
    path('events/<int:event_id>/feedback/submit',               views.submit_feedback,              name='submit_feedback_p'),
    path('events/<int:event_id>/gallery',                       views.get_event_gallery,            name='get_event_gallery_p'),
    path('events/<int:event_id>/gallery-full',                  views.get_event_gallery_full,       name='get_event_gallery_full'),
    path('events/<int:event_id>/gallery/upload',                views.upload_gallery_image,         name='upload_gallery_image_p'),
    path('events/<int:event_id>/upload-image',                  views.upload_gallery_image,         name='upload_image_alt'),
    path('events/<int:event_id>/gallery/<int:image_id>',        views.delete_gallery_image,         name='delete_gallery_image_p'),
    path('events/<int:event_id>/update',                        views.update_event,                 name='update_event_p'),
    path('events/<int:event_id>/delete',                        views.delete_event,                 name='delete_event_p'),
    path('events/<int:event_id>/cancel',                        views.cancel_event,                 name='cancel_event_p'),
    path('events/<int:event_id>/export-registrations',          views.export_registrations,         name='export_registrations'),
    path('events/<int:event_id>/waitlist',                      views.waitlist,                     name='waitlist'),
    path('events/<int:event_id>/waitlist-status',               views.waitlist_status,              name='waitlist_status'),
    path('events/<int:event_id>/coordinators',                  views.get_coordinators,             name='get_coordinators_p'),
    path('events/<int:event_id>/add-coordinator',               views.assign_coordinator,           name='assign_coordinator_p'),
    path('events/<int:event_id>/coordinators/<int:user_id>',    views.remove_coordinator,           name='remove_coordinator'),
    path('events/<int:event_id>/registrations',                 views.event_registrations_list,     name='event_registrations_list'),
    # FIX: unique names to avoid conflict with pages/urls.py president_views
    path('events/<int:event_id>/president-approve',             views.president_approve_event,      name='events_president_approve_event'),
    path('events/<int:event_id>/reject',                        views.president_reject_event,       name='events_president_reject_event'),

    # Singular prefix aliases
    path('event/<int:event_id>',                                views.get_event_detail,             name='get_event_detail'),
    path('event/<int:event_id>/update',                         views.update_event,                 name='update_event'),
    path('event/<int:event_id>/delete',                         views.delete_event,                 name='delete_event'),
    path('event/<int:event_id>/cancel',                         views.cancel_event,                 name='cancel_event'),
    path('event/<int:event_id>/gallery',                        views.get_event_gallery,            name='get_event_gallery'),
    path('event/<int:event_id>/gallery/upload',                 views.upload_gallery_image,         name='upload_gallery_image'),
    path('event/<int:event_id>/feedback',                       views.get_event_feedback,           name='get_event_feedback'),
    path('event/<int:event_id>/feedback/submit',                views.submit_feedback,              name='submit_feedback'),
    path('event/<int:event_id>/coordinators',                   views.get_coordinators,             name='get_coordinators'),
    path('event/<int:event_id>/assign-coordinator',             views.assign_coordinator,           name='assign_coordinator'),
    path('event/<int:event_id>/registrations',                  views.event_registrations_list,     name='event_registrations_list2'),

    # Upcoming
    path('upcoming-events',                                     views.upcoming_events,              name='upcoming_events'),

    # Club sub-routes
    path('club/<int:club_id>/events',                           views.club_events,                  name='club_events'),
    path('club-events/<int:club_id>',                           views.club_events,                  name='club_events_alt'),
    path('club/<int:club_id>/stats',                            views.club_stats,                   name='club_stats'),
    path('club/<int:club_id>/add-member',                       views.add_member,                   name='add_member'),
    path('club/<int:club_id>/manage-events',                    views.my_manageable_events,         name='manage_events'),
    path('club/<int:club_id>/event/<int:event_id>/edit',        views.member_edit_event,            name='member_edit_event'),
    path('club/<int:club_id>/events/<int:event_id>/request-delete', views.vp_request_event_delete, name='vp_request_delete'),

    # FIX: unique names to avoid conflict with pages/urls.py president_views
    path('pending-events/<int:club_id>',                        views.get_pending_events,           name='events_get_pending_events'),
    path('event-registrations/<int:event_id>',                  views.event_registrations_list,     name='event_registrations_alt'),
    path('my-coordinator-events',                               views.my_coordinator_events,        name='events_my_coordinator_events'),

    # QR Attendance
    path('events/<int:event_id>/qr/generate',   views.generate_qr_session, name='generate_qr_session'),
    path('events/<int:event_id>/qr/token',       views.get_qr_token,        name='get_qr_token'),
    path('events/<int:event_id>/qr/scan',        views.mark_attendance,     name='mark_attendance'),
    path('events/<int:event_id>/attendance',     views.get_attendance_list, name='get_attendance_list'),
]

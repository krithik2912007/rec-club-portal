from django.urls import path
from . import views

urlpatterns = [
    path('clubs',                                           views.get_clubs,                    name='get_clubs'),
    path('club/<int:club_id>',                              views.get_club_detail,              name='get_club_detail'),
    path('clubs/popular',                                   views.popular_clubs,                name='popular_clubs'),
    path('clubs/favourited',                                views.favourited_clubs,             name='favourited_clubs'),
    path('clubs/featured',                                  views.featured_clubs,               name='featured_clubs'),
    path('clubs/search',                                    views.search_clubs,                 name='search_clubs'),
    path('club/<int:club_id>/members',                      views.get_club_members,             name='get_club_members'),
    path('club/<int:club_id>/members-public',               views.get_club_members,             name='get_club_members_public'),

    # Favourite — both spellings, both prefixes
    path('club/<int:club_id>/favourite',                    views.toggle_favourite_club,        name='toggle_favourite_club'),
    path('clubs/<int:club_id>/favorite',                    views.toggle_favourite_club,        name='toggle_favourite_club2'),
    path('clubs/<int:club_id>/favourite',                   views.toggle_favourite_club,        name='toggle_favourite_club3'),

    path('club/<int:club_id>/past-events-gallery',          views.club_past_events_gallery,     name='club_past_events_gallery'),
    path('club/<int:club_id>/rejected-events',              views.get_rejected_events,          name='get_rejected_events'),
    path('user/favourite-clubs',                            views.user_favourite_clubs,         name='user_favourite_clubs'),

    # President / VP member management
    path('club/<int:club_id>/president/members',            views.president_get_members,      name='president_get_members'),
    path('club/<int:club_id>/president/members/<int:user_id>', views.president_member_detail, name='president_member_detail'),
    path('club/<int:club_id>/president/details',            views.president_update_club,      name='president_update_club'),
    path('club/<int:club_id>/my-changes',                   views.my_submitted_changes,       name='my_submitted_changes'),

    # Pending changes
    path('club/<int:club_id>/pending-changes',              views.get_pending_changes,        name='get_pending_changes'),
    path('club/<int:club_id>/pending-changes/<int:change_id>/approve', views.approve_pending_change, name='approve_pending_change'),
    path('club/<int:club_id>/pending-changes/<int:change_id>/reject',  views.reject_pending_change,  name='reject_pending_change'),
]

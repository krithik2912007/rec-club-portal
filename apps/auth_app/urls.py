from django.urls import path
from . import views

urlpatterns = [
    path('signup',                          views.signup,           name='signup'),
    path('login',                           views.login_view,       name='login'),
    path('logout',                          views.logout_view,      name='logout'),
    path('me',                              views.get_current_user, name='me'),
    path('api/my-clubs',                        views.my_clubs,         name='my_clubs'),
    path('switch-club',                     views.switch_club,      name='switch_club'),
    path('profile',                         views.get_profile,      name='get_profile'),
    path('profile/update',                  views.update_profile,   name='update_profile'),
    path('forgot-password',                 views.forgot_password,  name='forgot_password'),
    path('reset-password/<str:token>',      views.reset_password,   name='reset_password'),
    path('api/user-lookup',                 views.user_lookup,      name='user_lookup'),
]

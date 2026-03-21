from django.urls import path
from . import views

urlpatterns = [
    path('register',                                        views.register,                 name='register'),
    path('cancel-registration',                             views.cancel_registration,      name='cancel_registration'),
    path('cancel-registration/<int:event_id>',              views.cancel_registration_by_id,name='cancel_registration_by_id'),
    path('my-registrations',                                views.my_registrations,         name='my_registrations'),
    path('events/<int:event_id>/registrations',             views.event_registrations,      name='event_registrations'),
    path('events/<int:event_id>/registration-status',       views.registration_status,      name='registration_status'),
    path('registration-status/<int:event_id>',              views.registration_status,      name='registration_status2'),

    # Cart
    path('cart',                                            views.get_cart,                 name='get_cart'),
    path('cart/add',                                        views.add_to_cart,              name='add_to_cart'),
    path('cart/remove/<int:event_id>',                      views.remove_from_cart,         name='remove_from_cart'),
    path('cart/checkout',                                   views.checkout,                 name='checkout'),
    path('cart/confirm-payment',                            views.confirm_payment,          name='confirm_payment'),
    path('cart/payment-success',                            views.payment_success,          name='payment_success'),
    path('cart/check-pending',                              views.check_pending_payments,   name='check_pending_payments'),
    path('cart/payment-status/<int:payment_id>',            views.payment_status,           name='payment_status'),

    # Teams
    path('teams/create',                                    views.create_team,              name='create_team'),
    path('teams/register',                                  views.create_team,              name='team_register'),
    path('teams/join',                                      views.join_team,                name='join_team'),
    path('teams/validate-reg',                              views.validate_reg_no,          name='validate_reg_no'),
    path('events/<int:event_id>/teams',                     views.get_event_teams,          name='get_event_teams'),
    path('my-teams',                                        views.my_teams,                 name='my_teams'),
]

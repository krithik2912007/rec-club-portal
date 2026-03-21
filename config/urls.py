from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('',           include('apps.pages.urls')),
    path('',           include('apps.auth_app.urls')),
    path('api/',       include('apps.clubs.urls')),
    path('api/',       include('apps.events.urls')),
    path('api/',       include('apps.registrations.urls')),
    path('',       include('apps.admin_panel.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

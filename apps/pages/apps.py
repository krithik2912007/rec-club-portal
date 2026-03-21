from django.apps import AppConfig

class PagesConfig(AppConfig):
    name = 'apps.pages'

    def ready(self):
        from apps.ready import start_background_jobs
        start_background_jobs()

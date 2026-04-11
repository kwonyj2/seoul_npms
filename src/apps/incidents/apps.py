from django.apps import AppConfig

class IncidentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.incidents'
    verbose_name = '장애 관리'

    def ready(self):
        import apps.incidents.signals  # noqa: F401

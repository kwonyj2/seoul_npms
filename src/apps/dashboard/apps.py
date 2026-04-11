from django.apps import AppConfig

class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.dashboard'
    verbose_name = '대시보드'

    def ready(self):
        import apps.dashboard.signals  # noqa: F401

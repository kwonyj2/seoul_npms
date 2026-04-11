from django.apps import AppConfig


class WbsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.wbs'
    verbose_name = 'WBS 관리'

    def ready(self):
        import apps.wbs.signals  # noqa

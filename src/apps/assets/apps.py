from django.apps import AppConfig

class AssetsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.assets'
    verbose_name = '장비 관리'

    def ready(self):
        import apps.assets.signals  # noqa

from django.apps import AppConfig


class NasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.nas'
    verbose_name = 'NAS 파일 관리'

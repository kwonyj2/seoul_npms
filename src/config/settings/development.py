"""
개발 환경 설정
"""
import os
from .base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

# 개발 DB (로컬 PostgreSQL)
DATABASES['default']['HOST'] = env('DB_HOST', default='localhost')
DATABASES['default']['PORT'] = env('DB_PORT', default='5433')

# 개발 시 이메일 콘솔 출력
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# CORS (개발 시 전체 허용)
CORS_ALLOW_ALL_ORIGINS = True

# Django Debug Toolbar
INTERNAL_IPS = ['127.0.0.1']
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE

# 느린 쿼리 로그 임계값 (ms)
SLOW_QUERY_LOG_MS = 100

# 개발 시 Redis 없을 경우 캐시 비활성화
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# NAS 경로가 없는 개발 환경에서는 프로젝트 내 media/ 폴더로 대체
if not os.path.exists(NAS_ROOT):
    _dev_media = os.path.join(BASE_DIR, 'media')
    os.makedirs(_dev_media, exist_ok=True)
    MEDIA_ROOT      = _dev_media
    NAS_MEDIA_ROOT  = _dev_media
    NAS_OUTPUT_ROOT = os.path.join(_dev_media, '산출물')
    NAS_PHOTO_ROOT  = os.path.join(_dev_media, '작업이미지')
    for _d in [NAS_OUTPUT_ROOT, NAS_PHOTO_ROOT]:
        os.makedirs(_d, exist_ok=True)

# 로깅 (개발 — 모든 핸들러 콘솔 출력, 파일 없음)
_CONSOLE = {'class': 'logging.StreamHandler', 'formatter': 'verbose'}
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console':          _CONSOLE,
        'app_file':         _CONSOLE,
        'access_file':      _CONSOLE,
        'error_file':       _CONSOLE,
        'apps_error_file':  _CONSOLE,
        'security_file':    _CONSOLE,
        'celery_file':      _CONSOLE,
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
    'loggers': {
        'django':          {'handlers': ['console'], 'level': 'INFO',    'propagate': False},
        'django.request':  {'handlers': ['console', 'access_file', 'error_file'], 'level': 'INFO',    'propagate': False},
        'django.db.backends': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'django.security': {'handlers': ['console', 'security_file'],  'level': 'WARNING', 'propagate': False},
        'celery':          {'handlers': ['console', 'celery_file'],    'level': 'INFO',    'propagate': False},
        'celery.task':     {'handlers': ['console', 'celery_file'],    'level': 'INFO',    'propagate': False},
        'apps':            {'handlers': ['console', 'app_file'],       'level': 'DEBUG',   'propagate': False},
        'apps.errors':     {'handlers': ['console', 'apps_error_file'],'level': 'WARNING', 'propagate': False},
    },
}

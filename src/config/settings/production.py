"""
운영 환경 설정 (Docker)
"""
from .base import *

DEBUG = False  # 운영 환경에서는 절대 True 금지

# SECRET_KEY — 환경변수 필수, 기본값 없음 (미설정 시 기동 실패)
SECRET_KEY = env('SECRET_KEY')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['112.187.158.4', 'localhost'])

# ── /npms/ prefix 설정 (PMS와 충돌 방지) ─────────────────────────
FORCE_SCRIPT_NAME    = '/npms'
USE_X_FORWARDED_HOST = True

# 보안
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False  # HTTP 운영 시 False (HTTPS 전환 시 True)
CSRF_COOKIE_SECURE = False

# CSRF 신뢰 도메인
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[
    'http://localhost:8081',
    'http://127.0.0.1:8081',
    'http://112.187.158.4',
    'http://112.187.158.4:8081',
])

# CORS (운영 서버만 허용)
CORS_ALLOWED_ORIGINS = [
    'http://112.187.158.4',
    'http://localhost:8081',
]
CORS_ALLOW_CREDENTIALS = True

# 이메일
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')

import os as _os
_LOG_DIR = '/app/logs'
_os.makedirs(_LOG_DIR, exist_ok=True)

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
        # ── 콘솔 ──────────────────────────────
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        # ── 앱 전체 로그 (INFO+) ───────────────
        'app_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': f'{_LOG_DIR}/app.log',
            'maxBytes': 10 * 1024 * 1024,   # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        # ── HTTP 접근 로그 (INFO+, 모든 요청) ──
        'access_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': f'{_LOG_DIR}/access.log',
            'maxBytes': 20 * 1024 * 1024,   # 20 MB
            'backupCount': 30,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        # ── 에러 전용 로그 (ERROR+) ────────────
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': f'{_LOG_DIR}/error.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        # ── 앱 에러 전용 (apps.errors) ─────────
        'apps_error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': f'{_LOG_DIR}/error.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        # ── 보안 로그 ──────────────────────────
        'security_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': f'{_LOG_DIR}/security.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 30,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        # ── Celery 태스크 전용 로그 ─────────────
        'celery_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': f'{_LOG_DIR}/celery.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'root': {
        'handlers': ['console', 'app_file'],
        'level': 'INFO',
    },
    'loggers': {
        # Django 프레임워크
        'django':          {'handlers': ['console', 'app_file'],                      'level': 'WARNING', 'propagate': False},
        # HTTP 요청 — 접근로그(INFO) + 에러로그(ERROR)
        'django.request':  {'handlers': ['console', 'access_file', 'error_file'],     'level': 'INFO',    'propagate': False},
        # 보안 이벤트
        'django.security': {'handlers': ['console', 'security_file'],                 'level': 'WARNING', 'propagate': False},
        # Celery 태스크 실행
        'celery':          {'handlers': ['console', 'celery_file'],                   'level': 'INFO',    'propagate': False},
        'celery.task':     {'handlers': ['console', 'celery_file'],                   'level': 'INFO',    'propagate': False},
        # 앱 전체 (기본)
        'apps':            {'handlers': ['console', 'app_file'],                      'level': 'INFO',    'propagate': False},
        # 에러 전용 (core.error_views → apps.errors)
        'apps.errors':     {'handlers': ['console', 'apps_error_file'],               'level': 'WARNING', 'propagate': False},
        # DB 쿼리 — 느린 쿼리 감지 (SLOW_QUERY_LOG_MS 이상)
        'django.db.backends': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
    },
}
